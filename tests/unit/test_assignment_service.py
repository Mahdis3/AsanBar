"""
Unit tests برای AssignmentService
مهم‌ترین تست پروژه — race condition و distributed lock
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4
from contextlib import asynccontextmanager

from app.services.assignment_service import AssignmentService
from app.models.order import Order, OrderStatus
from app.models.driver import Driver, DriverStatus
from app.core.exceptions import (
    OrderAlreadyAssignedError, NoDriverAvailableError, NotFoundError
)


# ─── Helpers ───

def make_pending_order() -> Order:
    order = Order()
    order.id = uuid4()
    order.status = OrderStatus.PENDING
    order.pickup_location = {"lat": 35.7219, "lng": 51.3347, "address": "تهران"}
    order.dropoff_location = {"lat": 35.6892, "lng": 51.3890, "address": "تهران"}
    order.assigned_driver_id = None
    order.assigned_at = None
    return order


def make_available_driver() -> Driver:
    driver = Driver()
    driver.id = uuid4()
    driver.user_id = uuid4()
    driver.vehicle_plate = "11-AAA-111"
    driver.vehicle_type = "van"
    driver.status = DriverStatus.AVAILABLE
    driver.is_verified = True
    driver.rating = 4.8
    return driver


def make_redis_mock(nearby_drivers: list | None = None) -> AsyncMock:
    """Redis mock با GEO و lock."""
    redis = AsyncMock()

    # geosearch نتیجه برمی‌گردونه: [(driver_id, distance), ...]
    redis.geosearch.return_value = nearby_drivers or []
    redis.exists.return_value = 1  # driver آنلاینه

    # distributed lock — context manager
    lock_mock = AsyncMock()
    lock_mock.__aenter__ = AsyncMock(return_value=None)
    lock_mock.__aexit__ = AsyncMock(return_value=False)
    redis.lock.return_value = lock_mock

    redis.geoadd = AsyncMock()
    redis.setex = AsyncMock()
    redis.lpush = AsyncMock()
    redis.expire = AsyncMock()
    return redis


def make_db_mock(order: Order, drivers: list[Driver] | None = None) -> AsyncMock:
    db = AsyncMock()

    order_result = MagicMock()
    order_result.scalar_one_or_none.return_value = order

    driver_result = MagicMock()
    driver_result.scalars.return_value.all.return_value = drivers or []

    # اول order برمی‌گرده، بعد drivers
    db.execute.side_effect = [order_result, driver_result, order_result, driver_result]

    # begin() — context manager برای transaction
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin.return_value = begin_ctx
    db.flush = AsyncMock()

    return db


# ─── Tests: update_driver_location ───

@pytest.mark.asyncio
async def test_update_driver_location_stores_in_redis():
    driver_id = uuid4()
    redis = make_redis_mock()
    service = AssignmentService(AsyncMock(), redis)

    await service.update_driver_location(driver_id, lat=35.72, lng=51.33)

    redis.geoadd.assert_called_once_with(
        "drivers:location", [51.33, 35.72, str(driver_id)]
    )
    redis.setex.assert_called_once()
    # کلید TTL درست هست؟
    call_args = redis.setex.call_args[0]
    assert f"driver:online:{driver_id}" == call_args[0]
    assert call_args[1] == 300  # 5 دقیقه TTL


# ─── Tests: get_nearby_drivers ───

@pytest.mark.asyncio
async def test_get_nearby_drivers_returns_online_only():
    driver1_id = str(uuid4())
    driver2_id = str(uuid4())

    redis = make_redis_mock(nearby_drivers=[
        [driver1_id, "1.2"],
        [driver2_id, "3.5"],
    ])
    # driver2 آفلاینه
    redis.exists.side_effect = [1, 0]

    service = AssignmentService(AsyncMock(), redis)
    result = await service.get_nearby_drivers(lat=35.72, lng=51.33)

    assert len(result) == 1
    assert result[0]["driver_id"] == driver1_id
    assert result[0]["distance_km"] == 1.2


@pytest.mark.asyncio
async def test_get_nearby_drivers_empty():
    redis = make_redis_mock(nearby_drivers=[])
    service = AssignmentService(AsyncMock(), redis)

    result = await service.get_nearby_drivers(lat=35.72, lng=51.33)
    assert result == []


# ─── Tests: assign_nearest_driver ───

@pytest.mark.asyncio
async def test_assign_nearest_driver_success():
    order = make_pending_order()
    driver = make_available_driver()

    redis = make_redis_mock(nearby_drivers=[[str(driver.id), "2.1"]])
    db = make_db_mock(order, drivers=[driver])

    service = AssignmentService(db, redis)
    result = await service.assign_nearest_driver(order.id)

    assert result.id == driver.id
    assert order.status == OrderStatus.ASSIGNED
    assert order.assigned_driver_id == driver.id
    assert driver.status == DriverStatus.BUSY


@pytest.mark.asyncio
async def test_assign_already_assigned_order_raises():
    """Race condition: سفارش قبلاً تخصیص داده شده."""
    order = make_pending_order()
    order.status = OrderStatus.ASSIGNED  # ← قبلاً تخصیص داده شده

    redis = make_redis_mock(nearby_drivers=[[str(uuid4()), "1.0"]])
    db = make_db_mock(order)

    service = AssignmentService(db, redis)
    with pytest.raises(OrderAlreadyAssignedError):
        await service.assign_nearest_driver(order.id)


@pytest.mark.asyncio
async def test_assign_no_nearby_drivers_raises():
    """هیچ راننده‌ای نزدیک نیست."""
    order = make_pending_order()
    redis = make_redis_mock(nearby_drivers=[])
    db = make_db_mock(order)

    service = AssignmentService(db, redis)
    with pytest.raises(NoDriverAvailableError):
        await service.assign_nearest_driver(order.id)


@pytest.mark.asyncio
async def test_assign_no_available_driver_in_db_raises():
    """راننده‌ها نزدیکن ولی همه BUSY هستن."""
    order = make_pending_order()
    driver = make_available_driver()
    driver.status = DriverStatus.BUSY  # ← busy

    redis = make_redis_mock(nearby_drivers=[[str(driver.id), "1.0"]])
    db = make_db_mock(order, drivers=[])  # ← دیتابیس هیچ AVAILABLE برنمی‌گردونه

    service = AssignmentService(db, redis)
    with pytest.raises(NoDriverAvailableError):
        await service.assign_nearest_driver(order.id)


@pytest.mark.asyncio
async def test_assign_order_not_found_raises():
    redis = make_redis_mock()
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    service = AssignmentService(db, redis)
    with pytest.raises(NotFoundError):
        await service.assign_nearest_driver(uuid4())


@pytest.mark.asyncio
async def test_assign_uses_distributed_lock():
    """مطمئن میشیم lock گرفته میشه."""
    order = make_pending_order()
    driver = make_available_driver()

    redis = make_redis_mock(nearby_drivers=[[str(driver.id), "1.0"]])
    db = make_db_mock(order, drivers=[driver])

    service = AssignmentService(db, redis)
    await service.assign_nearest_driver(order.id)

    # lock باید با کلید درست گرفته شده باشه
    redis.lock.assert_called_once_with(
        f"lock:order:{order.id}", timeout=15, blocking_timeout=5
    )


@pytest.mark.asyncio
async def test_assign_picks_closest_driver():
    """از بین چند راننده، نزدیک‌ترین انتخاب میشه."""
    order = make_pending_order()

    driver_close = make_available_driver()
    driver_far = make_available_driver()

    nearby = [
        [str(driver_close.id), "1.0"],  # نزدیک‌تر — اول در لیست
        [str(driver_far.id), "4.5"],
    ]
    redis = make_redis_mock(nearby_drivers=nearby)

    db = AsyncMock()
    order_result = MagicMock()
    order_result.scalar_one_or_none.return_value = order

    driver_result = MagicMock()
    # هر دو available هستن
    driver_result.scalars.return_value.all.return_value = [driver_close, driver_far]

    db.execute.side_effect = [order_result, driver_result, order_result, driver_result]
    begin_ctx = MagicMock()
    begin_ctx.__aenter__ = AsyncMock(return_value=None)
    begin_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin.return_value = begin_ctx
    db.flush = AsyncMock()

    service = AssignmentService(db, redis)
    result = await service.assign_nearest_driver(order.id)

    assert result.id == driver_close.id
