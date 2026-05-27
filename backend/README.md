# Backend — Telegram Shop Platform

Python backend for Telegram Shop Platform.

## Stack

- Python 3.12+
- FastAPI
- Uvicorn
- SQLAlchemy 2.0 async ORM
- Alembic migrations
- PostgreSQL
- Redis
- Pydantic Settings
- Pytest

## Architecture

```text
app/
├── api/              # API router composition
├── common/           # shared dependencies, pagination, errors
├── core/             # config, security, app-level infrastructure
├── db/               # SQLAlchemy base/session/models
├── events/           # event names and dispatching contract
├── jobs/             # background job placeholders
├── modules/          # feature modules
│   ├── auth/
│   ├── users/
│   ├── products/
│   ├── categories/
│   ├── tags/
│   ├── banners/
│   ├── promo_codes/
│   ├── cart/
│   ├── orders/
│   ├── reviews/
│   ├── favorites/
│   ├── notifications/
│   ├── uploads/
│   ├── telegram/
│   └── statistics/
└── main.py
```

## Rules

- No Prisma in this backend.
- SQLAlchemy models + Alembic migrations define the database schema.
- FastAPI routers must not contain business logic.
- Services own business rules.
- Repositories own database queries.
- Pydantic schemas own request/response DTOs.
- Orders must be created inside DB transactions.
- Notifications must be emitted only after order persistence.
- Telegram is not a data source.
- Local storage must remain replaceable with S3/R2.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docker run

From project root:

```bash
docker compose up -d --build
```

## Alembic

Create migration:

```bash
alembic revision --autogenerate -m "init schema"
```

Apply migrations:

```bash
alembic upgrade head
```

## Health check

```bash
curl http://localhost:8000/health
```

## OpenAPI

FastAPI exposes OpenAPI at:

```text
http://localhost:8000/openapi.json
http://localhost:8000/docs
```
