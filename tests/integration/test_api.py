"""
تست‌های integration — نیاز به PostgreSQL و Redis دارند.
اجرا: pytest tests/integration/ -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from redis.asyncio import Redis

from app.main import app
from app.db.session import Base, get_db
from app.db.redis import get_redis
from app.core.config import settings

# ─── فیکسچرهای مشترک ───

TEST_DB_URL = settings.DATABASE_URL.replace("/asanbar_db", "/asanbar_test")


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


# ─── داده کمکی ───

CUSTOMER_DATA = {
    "email": "testcustomer@test.com",
    "phone": "09111111111",
    "full_name": "تست مشتری",
    "password": "Test@1234",
    "role": "customer",
}

COMPANY_DATA = {
    "email": "testcompany@test.com",
    "phone": "09222222222",
    "full_name": "شرکت تست",
    "password": "Test@1234",
    "role": "company",
}

DRIVER_DATA = {
    "email": "testdriver@test.com",
    "phone": "09333333333",
    "full_name": "تست راننده",
    "password": "Test@1234",
    "role": "driver",
}

ORDER_PAYLOAD = {
    "pickup_location": {"lat": 35.7219, "lng": 51.3347, "address": "تهران، میدان آزادی"},
    "dropoff_location": {"lat": 35.6892, "lng": 51.3890, "address": "تهران، میدان انقلاب"},
    "cargo_description": "بسته الکترونیکی",
    "cargo_weight_kg": 2.5,
}


# ─── Auth Tests ───

@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    # ثبت‌نام
    resp = await client.post("/api/v1/auth/register", json=CUSTOMER_DATA)
    assert resp.status_code == 201
    assert resp.json()["email"] == CUSTOMER_DATA["email"]

    # ورود
    resp = await client.post("/api/v1/auth/login", json={
        "email": CUSTOMER_DATA["email"],
        "password": CUSTOMER_DATA["password"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=CUSTOMER_DATA)
    resp = await client.post("/api/v1/auth/login", json={
        "email": CUSTOMER_DATA["email"],
        "password": "WrongPass!",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_register(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=CUSTOMER_DATA)
    resp = await client.post("/api/v1/auth/register", json=CUSTOMER_DATA)
    assert resp.status_code == 400


# ─── Order Tests ───

async def _get_token(client: AsyncClient, user_data: dict) -> str:
    await client.post("/api/v1/auth/register", json=user_data)
    resp = await client.post("/api/v1/auth/login", json={
        "email": user_data["email"], "password": user_data["password"]
    })
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_create_order(client: AsyncClient):
    token = await _get_token(client, CUSTOMER_DATA)
    resp = await client.post(
        "/api/v1/orders",
        json=ORDER_PAYLOAD,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["cargo_description"] == ORDER_PAYLOAD["cargo_description"]


@pytest.mark.asyncio
async def test_list_orders(client: AsyncClient):
    token = await _get_token(client, CUSTOMER_DATA)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/orders", json=ORDER_PAYLOAD, headers=headers)
    resp = await client.get("/api/v1/orders", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("healthy", "degraded")
