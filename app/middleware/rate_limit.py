import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.config import settings
from app.core.logging import logger


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting بر اساس نقش کاربر.
    COMPANY: 100 req/min | DRIVER: 60 req/min | سایر: 30 req/min
    """

    def __init__(self, app, redis=None):
        super().__init__(app)
        self._redis = redis

    async def dispatch(self, request: Request, call_next) -> Response:
        # Health check را رد می‌کنیم
        if request.url.path in ("/api/v1/health", "/docs", "/openapi.json"):
            return await call_next(request)

        redis = getattr(request.app.state, "redis", None)
        if not redis:
            return await call_next(request)

        # تشخیص نقش از JWT (بدون verify کامل — فقط برای rate limit)
        role = self._extract_role(request)
        limit = self._get_limit(role)
        identifier = self._get_identifier(request, role)

        key = f"rate_limit:{identifier}"
        now = int(time.time())
        window = now // 60  # پنجره ۱ دقیقه‌ای
        full_key = f"{key}:{window}"

        count = await redis.incr(full_key)
        if count == 1:
            await redis.expire(full_key, 65)  # کمی بیشتر از ۶۰ ثانیه

        if count > limit:
            logger.warning("rate_limit_exceeded", identifier=identifier, role=role, count=count)
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Too many requests. Limit: {limit}/min",
                },
                headers={"Retry-After": "60", "X-RateLimit-Limit": str(limit)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response

    def _extract_role(self, request: Request) -> str:
        try:
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return "anonymous"
            token = auth[7:]
            from jose import jwt as _jwt
            payload = _jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_exp": False},
            )
            return payload.get("role", "customer")
        except Exception:
            return "anonymous"

    def _get_limit(self, role: str) -> int:
        return {
            "company": settings.RATE_LIMIT_COMPANY,
            "driver": settings.RATE_LIMIT_DRIVER,
            "admin": 1000,
        }.get(role, settings.RATE_LIMIT_DEFAULT)

    def _get_identifier(self, request: Request, role: str) -> str:
        if role != "anonymous":
            auth = request.headers.get("Authorization", "")
            return f"user:{auth[-20:]}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"
