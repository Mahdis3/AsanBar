from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.core.exceptions import AppError, to_http_exception
from app.db.session import engine
from app.db.redis import get_redis
from app.api.v1.router import api_router
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.logging_middleware import RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup و Shutdown."""
    setup_logging()
    logger.info("app_starting", env=settings.APP_ENV)

    # اتصال Redis
    app.state.redis = await get_redis()
    logger.info("redis_connected")

    yield  # ─── اپ در حال اجرا ───

    # بستن اتصالات
    await app.state.redis.aclose()
    await engine.dispose()
    logger.info("app_shutdown")


app = FastAPI(
    title="AsanBar API",
    description="سیستم لجستیک هوشمند — Production-Level Demo",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middleware (ترتیب مهم است: اول اجرا شده = آخر add شده) ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# ─── Routers ───
app.include_router(api_router)


# ─── Global Exception Handlers ───
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    http_exc = to_http_exception(exc)
    return JSONResponse(status_code=http_exc.status_code, content=http_exc.detail)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    )


# ─── Health Check ───
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    """وضعیت سرویس."""
    redis_ok = False
    db_ok = False

    try:
        await app.state.redis.ping()
        redis_ok = True
    except Exception:
        pass

    try:
        from sqlalchemy import text
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    overall = "healthy" if (redis_ok and db_ok) else "degraded"
    return {
        "status": overall,
        "services": {
            "database": "up" if db_ok else "down",
            "redis": "up" if redis_ok else "down",
        },
        "version": "1.0.0",
        "env": settings.APP_ENV,
    }
