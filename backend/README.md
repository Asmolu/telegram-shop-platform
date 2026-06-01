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
http://localhost:8000/api/v1/openapi.json
http://localhost:8000/docs
```

## Authentication settings

Telegram login validates Mini App `initData` with `TELEGRAM_WEBAPP_BOT_TOKEN` or
`TELEGRAM_BOT_TOKEN`, then returns a JWT access token. Set `JWT_SECRET_KEY` to a
strong local secret before using authenticated endpoints.

Seller Portal email/password auth is exposed under `/api/v1/seller-auth`.
Public registration creates a SELLER account only after Bot 2 verification:

- `POST /seller-auth/register/start`
- `POST /telegram/seller-bot/webhook/<secret>` for Telegram Bot 2 webhook updates
- `POST /seller-auth/register/telegram-start` remains as the internal/manual
  service boundary used by the webhook flow
- `POST /seller-auth/register/confirm`
- `POST /seller-auth/login`
- `GET /seller-auth/me`

Use `TELEGRAM_BOT_TOKEN` for Bot 2. Set `TELEGRAM_SELLER_BOT_USERNAME` if the
API should return a direct `https://t.me/...` start link; otherwise the response
still includes the `/start seller_<token>` command. Set
`TELEGRAM_SELLER_WEBHOOK_SECRET` before exposing the webhook publicly.
Verification codes and passwords are stored hashed, not in plain text.

Set and verify the production Bot 2 webhook without printing the bot token:

```bash
python scripts/set_seller_bot_webhook.py set --base-url https://api.tsplatform.ru
python scripts/set_seller_bot_webhook.py info
```

## Notifications

Sprint 10 notifications are exposed under `/api/v1/notifications`.
Seller/admin management endpoints use `/api/v1/notifications/admin`.
User-facing notification listing is available at `/api/v1/notifications/me`.

Seller Telegram notifications use `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_SELLER_CHAT_ID`. `TELEGRAM_WEBAPP_BOT_TOKEN` remains reserved for Mini
App authentication and must not be used for seller notification delivery.

Seller bot management endpoints are exposed under `/api/v1/seller-bot`.
`/seller-bot/broadcast` targets only `TELEGRAM_SELLER_CHAT_ID` in the MVP and
creates audit log entries for seller/admin actions.
