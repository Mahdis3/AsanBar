"""
Unit tests برای OrderService
بدون نیاز به دیتابیس واقعی — از AsyncMock استفاده می‌کنیم
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.services.order_service import OrderService, VALID_TRANSITIONS
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.schemas.order import OrderCreateRequest, LocationSchema
from app.core.exceptions import NotFoundError, AppError, PermissionDeniedError


# ─── Fixtures ───

def make_user(role: UserRole = UserRole.CUSTOMER) -> User:
    user = User()
    user.id = uuid4()
    user.email = "test@test.com"
    user.role = role
    user.is_active = True
    return user


def make_order(status: OrderStatus = OrderStatus.PENDING) -> Order:
    order = Order()
    order.id = uuid4()
    order.customer_id = uuid4()
    order.assigned_driver_id = None
    order.status = status
    order.pickup_location = {"lat": 35.7, "lng": 51.3, "address": "تهران"}
    order.dropoff_location = {"lat": 35.6, "lng": 51.4, "address": "تهران"}
    order.cargo_description = "بسته تست"
    order.cargo_weight_kg = 2.0
    order.special_instructions = None
    order.created_at = datetime.now(timezone.utc)
    order.assigned_at = None
    order.picked_up_at = None
    order.delivered_at = None
    order.price = None
    return order


def make_db_mock(return_value=None) -> AsyncMock:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = return_value
    result_mock.scalars.return_value.all.return_value = [return_value] if return_value else []
    db.execute.return_value = result_mock
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


# ─── Tests: create_order ───

@pytest.mark.asyncio
async def test_create_order_success():
    customer = make_user(UserRole.CUSTOMER)
    db = make_db_mock()
    db.refresh = AsyncMock(side_effect=lambda o: None)

    data = OrderCreateRequest(
        pickup_location=LocationSchema(lat=35.7, lng=51.3, address="مبدا"),
        dropoff_location=LocationSchema(lat=35.6, lng=51.4, address="مقصد"),
        cargo_description="لپ‌تاپ",
        cargo_weight_kg=1.5,
    )

    service = OrderService(db)
    # چون refresh آبجکت رو پر نمی‌کنه در mock، مستقیم add رو چک می‌کنیم
    db.add = MagicMock()
    await service.create_order(data, customer)

    db.add.assert_called_once()
    db.commit.assert_called_once()


# ─── Tests: get_order ───

@pytest.mark.asyncio
async def test_get_order_found():
    order = make_order()
    db = make_db_mock(return_value=order)
    service = OrderService(db)

    result = await service.get_order(order.id)
    assert result.id == order.id


@pytest.mark.asyncio
async def test_get_order_not_found():
    db = make_db_mock(return_value=None)
    service = OrderService(db)

    with pytest.raises(NotFoundError):
        await service.get_order(uuid4())


# ─── Tests: update_status ───

@pytest.mark.asyncio
async def test_update_status_assigned_to_picked_up():
    order = make_order(OrderStatus.ASSIGNED)
    driver_user = make_user(UserRole.DRIVER)

    db = make_db_mock(return_value=order)

    # mock برای driver lookup
    from app.models.driver import Driver, DriverStatus
    driver = Driver()
    driver.id = uuid4()
    driver.user_id = driver_user.id
    order.assigned_driver_id = driver.id

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.side_effect = [order, driver]
    db.execute.return_value = result_mock

    service = OrderService(db)
    result = await service.update_status(order.id, "picked_up", driver_user)

    assert result.status == OrderStatus.PICKED_UP
    assert result.picked_up_at is not None


@pytest.mark.asyncio
async def test_update_status_invalid_transition():
    order = make_order(OrderStatus.PENDING)
    user = make_user(UserRole.ADMIN)
    db = make_db_mock(return_value=order)

    service = OrderService(db)
    with pytest.raises(AppError) as exc_info:
        await service.update_status(order.id, "delivered", user)
    assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


@pytest.mark.asyncio
async def test_update_status_invalid_status_string():
    order = make_order(OrderStatus.ASSIGNED)
    user = make_user(UserRole.ADMIN)
    db = make_db_mock(return_value=order)

    service = OrderService(db)
    with pytest.raises(AppError) as exc_info:
        await service.update_status(order.id, "flying", user)
    assert exc_info.value.code == "INVALID_STATUS"


# ─── Tests: VALID_TRANSITIONS ───

def test_valid_transitions_coverage():
    """مطمئن میشیم همه انتقال‌های معتبر تعریف شدن."""
    assert OrderStatus.PICKED_UP in VALID_TRANSITIONS[OrderStatus.ASSIGNED]
    assert OrderStatus.CANCELLED in VALID_TRANSITIONS[OrderStatus.ASSIGNED]
    assert OrderStatus.DELIVERED in VALID_TRANSITIONS[OrderStatus.PICKED_UP]
    assert OrderStatus.CANCELLED in VALID_TRANSITIONS[OrderStatus.PENDING]
