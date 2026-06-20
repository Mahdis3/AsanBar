# 🚚 AsanBar — Smart Logistics System

Production-grade sample project built with FastAPI + PostgreSQL + Redis

## Stack
- **FastAPI** — async REST API
- **PostgreSQL** — primary database
- **Redis** — distributed locking + driver geolocation (GEO)
- **SQLAlchemy (async)** — ORM
- **Alembic** — database migrations
- **Celery** — background task processing
- **pytest** — testing

## Quick Start

```bash
# 1. Copy environment variables
cp .env.example .env

# 2. Run with Docker
docker-compose up -d

# 3. Run migrations
docker-compose exec api alembic upgrade head

# 4. Load seed data
docker-compose exec api python scripts/seed.py

API Docs: http://localhost:8000/docs
```
Development (without Docker)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Ensure PostgreSQL and Redis are running locally
alembic upgrade head
uvicorn app.main:app --reload
```

Project Structure

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

| Method | Path | Description |
|--------|------|-------|
| POST | /api/v1/auth/register | User registration |
| POST | /api/v1/auth/login | User login |
| POST | /api/v1/orders | Create a new order |
| GET | /api/v1/orders/{id} | Get order details |
| POST | /api/v1/orders/{id}/assign | Assign a driver to an order |
| PUT | /api/v1/drivers/location | Update driver location |
| GET | /api/v1/drivers/nearby | Find nearby drivers |
| GET | /api/v1/health | Health check |
