import asyncio
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.models.order import Order, OrderStatus
from app.models.driver import Driver, DriverStatus
from app.core.exceptions import (
    OrderAlreadyAssignedError, NoDriverAvailableError, NotFoundError
)
from app.core.config import settings
from app.core.logging import logger


class AssignmentService:
    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    # ──────────────────────────────────────────────
    # موقعیت راننده در Redis (GEO)
    # ──────────────────────────────────────────────
    async def update_driver_location(
        self, driver_id: UUID, lat: float, lng: float
    ) -> None:
        """ذخیره موقعیت راننده با TTL 5 دقیقه در Redis GEO."""
        geo_key = "drivers:location"
        driver_key = f"driver:online:{driver_id}"

        await self.redis.geoadd(geo_key, [lng, lat, str(driver_id)])
        # TTL برای حذف راننده‌های آفلاین
        await self.redis.setex(driver_key, 300, "1")

        logger.debug("driver_location_updated", driver_id=str(driver_id), lat=lat, lng=lng)

    async def get_nearby_drivers(
        self, lat: float, lng: float, radius_km: float | None = None
    ) -> list[dict]:
        """راننده‌های نزدیک با فاصله."""
        radius = radius_km or settings.DRIVER_SEARCH_RADIUS_KM
        results = await self.redis.geosearch(
            "drivers:location",
            longitude=lng,
            latitude=lat,
            radius=radius,
            unit="km",
            sort="ASC",
            withcoord=False,
            withdist=True,
        )
        nearby = []
        for item in results:
            driver_id, distance = item[0], float(item[1])
            # بررسی آنلاین بودن راننده
            is_online = await self.redis.exists(f"driver:online:{driver_id}")
            if is_online:
                nearby.append({"driver_id": driver_id, "distance_km": distance})
        return nearby

    # ──────────────────────────────────────────────
    # تخصیص هوشمند با Distributed Lock
    # ──────────────────────────────────────────────
    async def assign_nearest_driver(self, order_id: UUID) -> Driver:
        """
        الگوریتم تخصیص با قفل توزیع‌شده Redis برای جلوگیری از Race Condition.
        """
        # گرفتن سفارش
        order = await self._get_order(order_id)
        if order.status != OrderStatus.PENDING:
            raise OrderAlreadyAssignedError()

        pickup = order.pickup_location
        nearby_raw = await self.get_nearby_drivers(
            lat=pickup["lat"], lng=pickup["lng"]
        )

        if not nearby_raw:
            raise NoDriverAvailableError()

        lock_key = f"lock:order:{order_id}"

        # قفل توزیع‌شده — timeout=15 ثانیه
        async with self.redis.lock(lock_key, timeout=15, blocking_timeout=5):
            # دوباره‌چک: کسی قبل از ما قفل را نگرفته؟
            order = await self._get_order(order_id)
            if order.status != OrderStatus.PENDING:
                raise OrderAlreadyAssignedError()

            best_driver = await self._pick_best_available_driver(nearby_raw)
            if not best_driver:
                raise NoDriverAvailableError()

            # تراکنش اتمیک در PostgreSQL
            async with self.db.begin():
                order.status = OrderStatus.ASSIGNED
                order.assigned_driver_id = best_driver.id
                order.assigned_at = datetime.now(timezone.utc)
                best_driver.status = DriverStatus.BUSY
                await self.db.flush()

        # fire-and-forget: اعلان راننده
        asyncio.create_task(
            self._notify_driver(best_driver.id, order_id)
        )

        logger.info(
            "order_assigned",
            order_id=str(order_id),
            driver_id=str(best_driver.id),
        )
        return best_driver

    async def _pick_best_available_driver(
        self, nearby_raw: list[dict]
    ) -> Driver | None:
        """
        از بین راننده‌های نزدیک، اولین AVAILABLE را با کمترین فاصله برمی‌گرداند.
        (می‌توان با rating یا تعداد deliveries وزن‌دهی کرد)
        """
        driver_ids = [item["driver_id"] for item in nearby_raw]
        result = await self.db.execute(
            select(Driver).where(
                Driver.id.in_(driver_ids),
                Driver.status == DriverStatus.AVAILABLE,
                Driver.is_verified == True,
            )
        )
        drivers_map = {str(d.id): d for d in result.scalars().all()}

        # ترتیب بر اساس فاصله (nearby_raw از قبل sort شده)
        for item in nearby_raw:
            driver = drivers_map.get(item["driver_id"])
            if driver:
                return driver
        return None

    async def _get_order(self, order_id: UUID) -> Order:
        result = await self.db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise NotFoundError("Order", str(order_id))
        return order

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(Exception),
        reraise=False,
    )
    async def _notify_driver(self, driver_id: UUID, order_id: UUID) -> None:
        """
        شبیه‌سازی ارسال Push Notification.
        در پروداکشن: Firebase FCM / RabbitMQ / Webhook
        """
        notif_key = f"notification:driver:{driver_id}"
        payload = f'{{"order_id": "{order_id}", "action": "new_order"}}'
        await self.redis.lpush(notif_key, payload)
        await self.redis.expire(notif_key, 300)

        logger.info("driver_notified", driver_id=str(driver_id), order_id=str(order_id))
