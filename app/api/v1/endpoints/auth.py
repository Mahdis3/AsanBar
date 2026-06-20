from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest
from app.services.auth_service import AuthService
from app.core.exceptions import AppError, to_http_exception

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """ثبت‌نام کاربر جدید."""
    try:
        service = AuthService(db)
        user = await service.register(data)
        return {"id": str(user.id), "email": user.email, "role": user.role.value}
    except AppError as e:
        raise to_http_exception(e)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """ورود و دریافت توکن."""
    try:
        service = AuthService(db)
        return await service.login(data)
    except AppError as e:
        raise to_http_exception(e)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """تجدید توکن دسترسی."""
    try:
        service = AuthService(db)
        return await service.refresh(data.refresh_token)
    except AppError as e:
        raise to_http_exception(e)
