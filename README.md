# 🚚 AsanBar — سیستم لجستیک هوشمند

پروژه نمونه Production-Level با FastAPI + PostgreSQL + Redis

## Stack
- **FastAPI** — async REST API
- **PostgreSQL** — دیتابیس اصلی
- **Redis** — قفل توزیع‌شده + موقعیت راننده (GEO)
- **SQLAlchemy (async)** — ORM
- **Alembic** — migration
- **Celery** — background tasks
- **pytest** — تست

## راه‌اندازی سریع

```bash
# 1. کپی env
cp .env.example .env

# 2. اجرا با Docker
docker-compose up -d

# 3. اعمال migration
docker-compose exec api alembic upgrade head

# 4. بارگذاری داده اولیه
docker-compose exec api python scripts/seed.py
```

API Docs: http://localhost:8000/docs

## اجرا بدون Docker (توسعه)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# PostgreSQL و Redis باید در حال اجرا باشند
alembic upgrade head
uvicorn app.main:app --reload
```

## ساختار پروژه

```
asanbar/
├── app/
│   ├── api/v1/endpoints/   # Route handlers
│   ├── core/               # Config, security, logging
│   ├── db/                 # Database session, base
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Business logic
│   └── middleware/         # Rate limiting, logging
├── tests/
│   ├── unit/
│   └── integration/
├── alembic/                # DB migrations
└── scripts/                # Seed data
```

## API Endpoints

| Method | Path | توضیح |
|--------|------|-------|
| POST | /api/v1/auth/register | ثبت‌نام |
| POST | /api/v1/auth/login | ورود |
| POST | /api/v1/orders | ثبت سفارش |
| GET | /api/v1/orders/{id} | جزئیات سفارش |
| POST | /api/v1/orders/{id}/assign | تخصیص راننده |
| PUT | /api/v1/drivers/location | آپدیت موقعیت راننده |
| GET | /api/v1/drivers/nearby | راننده‌های نزدیک |
| GET | /api/v1/health | Health check |
