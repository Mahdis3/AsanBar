from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.session import get_db
from app.db.redis import get_redis
from app.api.deps import get_current_user, require_roles
from app.models.user import User, UserRole
from app.schemas.order import OrderCreateRequest, OrderResponse, OrderStatusUpdateRequest
from app.services.order_service import OrderService
from app.services.assignment_service import AssignmentService
from app.core.exceptions import AppError, to_http_exception

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order(
    data: OrderCreateRequest,
    current_user: User = Depends(require_roles(UserRole.CUSTOMER, UserRole.COMPANY, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """ثبت سفارش جدید."""
    try:
        service = OrderService(db)
        order = await service.create_order(data, current_user)
        return order
    except AppError as e:
        raise to_http_exception(e)


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """لیست سفارش‌ها."""
    service = OrderService(db)
    return await service.list_orders(current_user, skip=skip, limit=limit)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """جزئیات سفارش."""
    try:
        service = OrderService(db)
        return await service.get_order(order_id)
    except AppError as e:
        raise to_http_exception(e)


@router.post("/{order_id}/assign", response_model=dict)
async def assign_order(
    order_id: UUID,
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.COMPANY)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """تخصیص هوشمند سفارش به نزدیک‌ترین راننده."""
    try:
        service = AssignmentService(db, redis)
        driver = await service.assign_nearest_driver(order_id)
        return {
            "message": "Order assigned successfully",
            "driver_id": str(driver.id),
            "vehicle_plate": driver.vehicle_plate,
        }
    except AppError as e:
        raise to_http_exception(e)


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: UUID,
    data: OrderStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """آپدیت وضعیت سفارش (راننده یا ادمین)."""
    try:
        service = OrderService(db)
        return await service.update_status(order_id, data.status, current_user)
    except AppError as e:
        raise to_http_exception(e)
