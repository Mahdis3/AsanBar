from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.session import get_db
from app.db.redis import get_redis
from app.api.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.schemas.driver import DriverLocationUpdate, DriverProfileResponse, DriverRegisterRequest, NearbyDriverResponse
from app.services.driver_service import DriverService
from app.services.assignment_service import AssignmentService
from app.core.exceptions import AppError, to_http_exception

router = APIRouter(prefix="/drivers", tags=["Drivers"])


@router.post("/profile", response_model=DriverProfileResponse, status_code=201)
async def register_driver_profile(
    data: DriverRegisterRequest,
    current_user: User = Depends(require_roles(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    """ساخت پروفایل راننده."""
    try:
        service = DriverService(db)
        return await service.register_driver_profile(current_user, data)
    except AppError as e:
        raise to_http_exception(e)


@router.get("/profile/me", response_model=DriverProfileResponse)
async def get_my_profile(
    current_user: User = Depends(require_roles(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    """پروفایل راننده جاری."""
    try:
        service = DriverService(db)
        return await service.get_driver_by_user(current_user)
    except AppError as e:
        raise to_http_exception(e)


@router.put("/location", response_model=dict)
async def update_location(
    data: DriverLocationUpdate,
    current_user: User = Depends(require_roles(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """آپدیت موقعیت راننده در Redis."""
    try:
        driver_service = DriverService(db)
        driver = await driver_service.get_driver_by_user(current_user)

        assignment_service = AssignmentService(db, redis)
        await assignment_service.update_driver_location(driver.id, data.lat, data.lng)
        return {"message": "Location updated", "lat": data.lat, "lng": data.lng}
    except AppError as e:
        raise to_http_exception(e)


@router.patch("/availability", response_model=DriverProfileResponse)
async def set_availability(
    available: bool,
    current_user: User = Depends(require_roles(UserRole.DRIVER)),
    db: AsyncSession = Depends(get_db),
):
    """تغییر وضعیت در دسترس بودن راننده."""
    try:
        service = DriverService(db)
        return await service.set_availability(current_user, available)
    except AppError as e:
        raise to_http_exception(e)


@router.get("/nearby", response_model=list[NearbyDriverResponse])
async def get_nearby_drivers(
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPANY)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """راننده‌های آنلاین نزدیک به یک موقعیت."""
    service = AssignmentService(db, redis)
    return await service.get_nearby_drivers(lat, lng, radius_km)
