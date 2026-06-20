"""
Integration tests — flow کامل تخصیص و rate limiting
نیاز به PostgreSQL و Redis دارند.
"""
import pytest
import pytest_asyncio
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from redis.asyncio import Redis

from app.main import app
from app.db.session import Base, get_db
from app.db.redis import get_redis
from app.core.config import settings

TEST_DB_URL = settings.DATABASE_URL.replace("/asanbar_db", "/asanbar_test")

# ─── Fixtures (مشترک با test_api.py) ───

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def redis_client():
    r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield r
    await r.flushdb()
    await r.aclose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, redis_client: Redis):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: redis_client
    app.state.redis = redis_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ─── Helpers ───

async def register_and_login(client: AsyncClient, data: dict) -> str:
    await client.post("/api/v1/auth/register", json=data)
    resp = await client.post("/api/v1/auth/login", json={
        "email": data["email"], "password": data["password"]
    })
    return resp.json()["access_token"]


COMPANY = {"email": "co@flow.com", "phone": "09400000001", "full_name": "شرکت", "password": "Test@1234", "role": "company"}
DRIVER = {"email": "dr@flow.com", "phone": "09400000002", "full_name": "راننده", "password": "Test@1234", "role": "driver"}
CUSTOMER = {"email": "cu@flow.com", "phone": "09400000003", "full_name": "مشتری", "password": "Test@1234", "role": "customer"}

ORDER = {
    "pickup_location": {"lat": 35.7219, "lng": 51.3347, "address": "میدان آزادی"},
    "dropoff_location": {"lat": 35.6892, "lng": 51.3890, "address": "میدان انقلاب"},
    "cargo_description": "بسته تست flow",
    "cargo_weight_kg": 3.0,
}


# ─── Tests: Full Assignment Flow ───

@pytest.mark.asyncio
async def test_full_order_assignment_flow(client: AsyncClient, redis_client: Redis):
    """
    Flow کامل:
    ۱. مشتری سفارش ثبت می‌کنه
    ۲. راننده آنلاین میشه و موقعیتش رو آپدیت می‌کنه
    ۳. شرکت سفارش رو به راننده تخصیص میده
    ۴. راننده وضعیت رو به picked_up تغییر میده
    ۵. راننده وضعیت رو به delivered تغییر میده
    """
    company_token = await register_and_login(client, COMPANY)
    driver_token = await register_and_login(client, DRIVER)
    customer_token = await register_and_login(client, CUSTOMER)

    # ۱. ساخت پروفایل راننده
    resp = await client.post(
        "/api/v1/drivers/profile",
        json={"vehicle_plate": "99-ZZZ-999", "vehicle_type": "van"},
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert resp.status_code == 201

    # تأیید راننده در دیتابیس (در پروداکشن توسط ادمین انجام میشه)
    from sqlalchemy import text
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await db.execute(text("UPDATE drivers SET is_verified=true, status='available'"))
        await db.commit()

    # ۲. راننده موقعیتش رو آپدیت می‌کنه (نزدیک به pickup سفارش)
    resp = await client.put(
        "/api/v1/drivers/location",
        json={"lat": 35.7200, "lng": 51.3340},  # ~300 متر از pickup
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert resp.status_code == 200

    # ۳. مشتری سفارش ثبت می‌کنه
    resp = await client.post(
        "/api/v1/orders",
        json=ORDER,
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert resp.status_code == 201
    order_id = resp.json()["id"]

    # ۴. شرکت تخصیص میده
    resp = await client.post(
        f"/api/v1/orders/{order_id}/assign",
        headers={"Authorization": f"Bearer {company_token}"},
    )
    assert resp.status_code == 200
    assert "driver_id" in resp.json()

    # ۵. بررسی وضعیت سفارش
    resp = await client.get(
        f"/api/v1/orders/{order_id}",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert resp.json()["status"] == "assigned"

    # ۶. راننده pickup می‌کنه
    resp = await client.patch(
        f"/api/v1/orders/{order_id}/status",
        json={"status": "picked_up"},
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["picked_up_at"] is not None

    # ۷. راننده تحویل میده
    resp = await client.patch(
        f"/api/v1/orders/{order_id}/status",
        json={"status": "delivered"},
        headers={"Authorization": f"Bearer {driver_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "delivered"
    assert resp.json()["delivered_at"] is not None


@pytest.mark.asyncio
async def test_assign_order_no_driver_available(client: AsyncClient):
    """تخصیص وقتی هیچ راننده‌ای نزدیک نیست."""
    company_token = await register_and_login(client, COMPANY)
    customer_token = await register_and_login(client, CUSTOMER)

    resp = await client.post(
        "/api/v1/orders",
        json=ORDER,
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    order_id = resp.json()["id"]

    # بدون اینکه راننده‌ای موقعیت داده باشه
    resp = await client.post(
        f"/api/v1/orders/{order_id}/assign",
        headers={"Authorization": f"Bearer {company_token}"},
    )
    assert resp.status_code == 503  # NO_DRIVER_AVAILABLE


@pytest.mark.asyncio
async def test_cancel_pending_order(client: AsyncClient):
    """لغو سفارش pending."""
    company_token = await register_and_login(client, COMPANY)
    customer_token = await register_and_login(client, CUSTOMER)

    resp = await client.post(
        "/api/v1/orders", json=ORDER,
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    order_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers={"Authorization": f"Bearer {company_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# ─── Tests: Rate Limiting ───

@pytest.mark.asyncio
async def test_rate_limit_anonymous_user(client: AsyncClient, redis_client: Redis):
    """کاربر anonymous بعد از ۳۰ درخواست باید ۴۲۹ بگیره."""
    await redis_client.flushdb()

    responses = []
    for _ in range(35):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "x@x.com", "password": "wrong"}
        )
        responses.append(resp.status_code)

    assert 429 in responses, "باید rate limit فعال بشه"
    last_429 = next(r for r in reversed(responses) if r == 429)
    assert last_429 == 429


@pytest.mark.asyncio
async def test_rate_limit_headers_present(client: AsyncClient):
    """هدرهای rate limit باید در response باشن."""
    resp = await client.get("/api/v1/health")
    # health check bypass میشه ولی سایر endpointها هدر دارن
    resp2 = await client.post(
        "/api/v1/auth/login",
        json={"email": "x@x.com", "password": "wrong"}
    )
    assert "x-ratelimit-limit" in resp2.headers
    assert "x-ratelimit-remaining" in resp2.headers


# ─── Tests: Authorization ───

@pytest.mark.asyncio
async def test_customer_cannot_assign_order(client: AsyncClient):
    """مشتری نمی‌تونه تخصیص بده."""
    customer_token = await register_and_login(client, CUSTOMER)

    resp = await client.post(
        f"/api/v1/orders/{str(__import__('uuid').uuid4())}/assign",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(client: AsyncClient):
    """بدون توکن باید ۴۰۱ برگرده."""
    resp = await client.get("/api/v1/orders")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_returns_401(client: AsyncClient):
    resp = await client.get(
        "/api/v1/orders",
        headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert resp.status_code == 401
