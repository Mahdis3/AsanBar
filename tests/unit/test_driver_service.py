"""
Unit tests برای DriverService
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.driver_service import DriverService
from app.models.driver import Driver, DriverStatus
from app.models.user import User, UserRole
from app.schemas.driver import DriverRegisterRequest
from app.core.exceptions import NotFoundError, PermissionDeniedError, AppError


# ─── Helpers ───

def make_user(role: UserRole = UserRole.DRIVER) -> User:
    user = User()
    user.id = uuid4()
    user.email = "driver@test.com"
    user.role = role
    return user


def make_driver(user_id=None, verified=True) -> Driver:
    driver = Driver()
    driver.id = uuid4()
    driver.user_id = user_id or uuid4()
    driver.vehicle_plate = "11-AAA-111"
    driver.vehicle_type = "van"
    driver.status = DriverStatus.OFFLINE
    driver.is_verified = verified
    driver.rating = 5.0
    driver.total_deliveries = 0
    return driver


def make_db_mock(return_value=None) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = return_value
    db.execute.return_value = result
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ─── Tests: register_driver_profile ───

@pytest.mark.asyncio
async def test_register_driver_profile_success():
    user = make_user(UserRole.DRIVER)
    db = make_db_mock(return_value=None)  # پروفایل وجود نداره

    data = DriverRegisterRequest(vehicle_plate="22-BBB-222", vehicle_type="truck")
    service = DriverService(db)
    await service.register_driver_profile(user, data)

    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_register_driver_non_driver_role_raises():
    """فقط نقش DRIVER می‌تونه پروفایل راننده بسازه."""
    user = make_user(UserRole.CUSTOMER)
    db = make_db_mock()

    data = DriverRegisterRequest(vehicle_plate="33-CCC-333", vehicle_type="van")
    service = DriverService(db)

    with pytest.raises(PermissionDeniedError):
        await service.register_driver_profile(user, data)


@pytest.mark.asyncio
async def test_register_driver_duplicate_raises():
    """پروفایل تکراری نباید ساخته بشه."""
    user = make_user(UserRole.DRIVER)
    existing_driver = make_driver(user_id=user.id)
    db = make_db_mock(return_value=existing_driver)  # قبلاً ساخته شده

    data = DriverRegisterRequest(vehicle_plate="44-DDD-444", vehicle_type="van")
    service = DriverService(db)

    with pytest.raises(AppError) as exc_info:
        await service.register_driver_profile(user, data)
    assert exc_info.value.code == "DUPLICATE_DRIVER"


# ─── Tests: get_driver_by_user ───

@pytest.mark.asyncio
async def test_get_driver_by_user_found():
    user = make_user()
    driver = make_driver(user_id=user.id)
    db = make_db_mock(return_value=driver)

    service = DriverService(db)
    result = await service.get_driver_by_user(user)
    assert result.id == driver.id


@pytest.mark.asyncio
async def test_get_driver_by_user_not_found():
    user = make_user()
    db = make_db_mock(return_value=None)

    service = DriverService(db)
    with pytest.raises(NotFoundError):
        await service.get_driver_by_user(user)


# ─── Tests: set_availability ───

@pytest.mark.asyncio
async def test_set_available_verified_driver():
    user = make_user()
    driver = make_driver(user_id=user.id, verified=True)
    db = make_db_mock(return_value=driver)

    service = DriverService(db)
    result = await service.set_availability(user, available=True)

    assert result.status == DriverStatus.AVAILABLE
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_set_offline():
    user = make_user()
    driver = make_driver(user_id=user.id, verified=True)
    driver.status = DriverStatus.AVAILABLE
    db = make_db_mock(return_value=driver)

    service = DriverService(db)
    result = await service.set_availability(user, available=False)

    assert result.status == DriverStatus.OFFLINE


@pytest.mark.asyncio
async def test_set_availability_unverified_raises():
    """راننده تأییدنشده نمی‌تونه آنلاین بشه."""
    user = make_user()
    driver = make_driver(user_id=user.id, verified=False)
    db = make_db_mock(return_value=driver)

    service = DriverService(db)
    with pytest.raises(AppError) as exc_info:
        await service.set_availability(user, available=True)
    assert exc_info.value.code == "NOT_VERIFIED"
