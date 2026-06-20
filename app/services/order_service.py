from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.schemas.order import OrderCreateRequest
from app.core.exceptions import NotFoundError, PermissionDeniedError, AppError
from app.core.logging import logger


VALID_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    OrderStatus.ASSIGNED: [OrderStatus.PICKED_UP, OrderStatus.CANCELLED],
    OrderStatus.PICKED_UP: [OrderStatus.DELIVERED],
    OrderStatus.PENDING: [OrderStatus.CANCELLED],
}


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_order(self, data: OrderCreateRequest, customer: User) -> Order:
        order = Order(
            customer_id=customer.id,
            pickup_location=data.pickup_location.model_dump(),
            dropoff_location=data.dropoff_location.model_dump(),
            cargo_description=data.cargo_description,
            cargo_weight_kg=data.cargo_weight_kg,
            special_instructions=data.special_instructions,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        logger.info("order_created", order_id=str(order.id), customer_id=str(customer.id))
        return order

    async def get_order(self, order_id: UUID) -> Order:
        result = await self.db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise NotFoundError("Order", str(order_id))
        return order

    async def list_orders(self, user: User, skip: int = 0, limit: int = 20) -> list[Order]:
        from app.models.user import UserRole
        if user.role in (UserRole.ADMIN, UserRole.COMPANY):
            stmt = select(Order).order_by(Order.created_at.desc()).offset(skip).limit(limit)
        else:
            stmt = (
                select(Order)
                .where(Order.customer_id == user.id)
                .order_by(Order.created_at.desc())
                .offset(skip).limit(limit)
            )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, order_id: UUID, new_status_str: str, actor: User) -> Order:
        order = await self.get_order(order_id)

        try:
            new_status = OrderStatus(new_status_str)
        except ValueError:
            raise AppError(f"Invalid status: {new_status_str}", "INVALID_STATUS")

        # اعتبارسنجی انتقال وضعیت
        allowed = VALID_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            raise AppError(
                f"Cannot transition from {order.status} to {new_status}",
                "INVALID_STATUS_TRANSITION"
            )

        # راننده فقط سفارش خودش را می‌تواند آپدیت کند
        from app.models.user import UserRole
        if actor.role == UserRole.DRIVER:
            driver_result = await self.db.execute(
                select(__import__("app.models.driver", fromlist=["Driver"]).Driver)
                .where(__import__("app.models.driver", fromlist=["Driver"]).Driver.user_id == actor.id)
            )
            driver = driver_result.scalar_one_or_none()
            if not driver or order.assigned_driver_id != driver.id:
                raise PermissionDeniedError()

        now = datetime.now(timezone.utc)
        order.status = new_status
        if new_status == OrderStatus.PICKED_UP:
            order.picked_up_at = now
        elif new_status == OrderStatus.DELIVERED:
            order.delivered_at = now

        await self.db.commit()
        await self.db.refresh(order)

        logger.info("order_status_updated",
                    order_id=str(order_id),
                    new_status=new_status,
                    actor_id=str(actor.id))
        return order
