from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.core.exceptions import AuthenticationError, AppError
from app.core.logging import logger


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: RegisterRequest) -> User:
        # بررسی تکراری نبودن ایمیل
        existing = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        if existing.scalar_one_or_none():
            raise AppError("Email already registered", "DUPLICATE_EMAIL")

        # بررسی نقش معتبر
        try:
            role = UserRole(data.role)
        except ValueError:
            raise AppError(f"Invalid role: {data.role}", "INVALID_ROLE")

        user = User(
            email=data.email,
            phone=data.phone,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            role=role,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info("user_registered", user_id=str(user.id), email=user.email, role=role)
        return user

    async def login(self, data: LoginRequest) -> TokenResponse:
        result = await self.db.execute(
            select(User).where(User.email == data.email, User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(data.password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        access_token = create_access_token(
            subject=str(user.id),
            extra={"role": user.role.value}
        )
        refresh_token = create_refresh_token(subject=str(user.id))

        logger.info("user_logged_in", user_id=str(user.id))
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise AuthenticationError("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise AuthenticationError("Token is not a refresh token")

        user_id = payload.get("sub")
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise AuthenticationError("User not found")

        new_access = create_access_token(str(user.id), extra={"role": user.role.value})
        new_refresh = create_refresh_token(str(user.id))
        return TokenResponse(access_token=new_access, refresh_token=new_refresh)

    async def get_current_user(self, token: str) -> User:
        try:
            payload = decode_token(token)
        except ValueError:
            raise AuthenticationError("Invalid or expired token")

        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")

        user_id = payload.get("sub")
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise AuthenticationError("User not found or inactive")
        return user
