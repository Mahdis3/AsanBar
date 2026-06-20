from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.driver import Driver, DriverStatus
from app.models.user import User, UserRole
from app.schemas.driver import DriverRegisterRequest
from app.core.exceptions import NotFoundError, PermissionDeniedError, AppError
from app.core.logging import logger


class DriverService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_driver_profile(
        self, user: User, data: DriverRegisterRequest
    ) -> Driver:
        if user.role != UserRole.DRIVER:
            raise PermissionDeniedError()

        existing = await self.db.execute(
            select(Driver).where(Driver.user_id == user.id)
        )
        if existing.scalar_one_or_none():
            raise AppError("Driver profile already exists", "DUPLICATE_DRIVER")

        driver = Driver(
            user_id=user.id,
            vehicle_plate=data.vehicle_plate,
            vehicle_type=data.vehicle_type,
        )
        self.db.add(driver)
        await self.db.commit()
        await self.db.refresh(driver)
        logger.info("driver_profile_created", driver_id=str(driver.id))
        return driver

    async def get_driver_by_user(self, user: User) -> Driver:
        result = await self.db.execute(
            select(Driver).where(Driver.user_id == user.id)
        )
        driver = result.scalar_one_or_none()
        if not driver:
            raise NotFoundError("Driver profile", str(user.id))
        return driver

    async def set_availability(self, user: User, available: bool) -> Driver:
        driver = await self.get_driver_by_user(user)
        if not driver.is_verified:
            raise AppError("Driver not verified yet", "NOT_VERIFIED")
        driver.status = DriverStatus.AVAILABLE if available else DriverStatus.OFFLINE
        await self.db.commit()
        await self.db.refresh(driver)
        return driver
