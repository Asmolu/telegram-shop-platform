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

## Idempotency

Critical customer mutations can use the `Idempotency-Key` header:

- `POST /api/v1/orders/checkout`
- `POST /api/v1/orders/{order_id}/payment/submit`
- `POST /api/v1/orders/{order_id}/payment/receipt`

The backend stores the key with user id, endpoint scope, request payload hash,
the successful response body, and a 24 hour expiration. A retry with the same
key and same payload replays the original success response. A retry with the
same key and different payload returns `409 Conflict`. Concurrent requests with
the same key are serialized by the database unique constraint and row lock.
Clients that do not send the header remain compatible, but do not receive
server-side replay protection beyond the existing transaction and status rules.

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

## Public catalog API contract

Public product list contexts use a compact card DTO:

- `GET /api/v1/products` returns `ProductCardList`.
- Card items include identity, display price, badge fields, availability,
  `image_url` for the card-sized image, `thumbnail_image_url`, fixed 4:5 image
  dimensions, and compact active variants.
- Card variants include only `id`, `size`, `color`, `available_quantity`, and
  `is_active`. SKU, raw stock, reserved stock, timestamps, descriptions, full
  category/tag objects, full galleries, and related products are intentionally
  omitted.
- `GET /api/v1/products/{id}` returns the public detail DTO with description,
  public gallery URLs and variants, active variants including visible SKU,
  taxonomy summaries, and related products as compact card DTOs.
- Seller Panel keeps using `/api/v1/products/admin` and
  `/api/v1/products/admin/{id}` for the full admin DTO.

Public catalog responses can use conditional requests:

- Products, product detail, and banners return `ETag` with
  `Cache-Control: no-cache`.
- Categories and tags return `ETag` with
  `Cache-Control: public, max-age=60, stale-while-revalidate=300`.
- Personalized endpoints such as cart and favorites return
  `Cache-Control: private, no-store`.

The compact list contract is a coordinated backend + Mini App rollout. Older
Mini App builds that require full `images`, `tags`, and `categories` on product
lists should not be served against the compact-only backend.

## Privacy-safe telemetry

Mini App telemetry is handled by the existing analytics module:

- `POST /api/v1/analytics/telemetry` accepts strict schema-versioned batches and
  returns only compact accepted/sampled counts.
- The endpoint is optional-auth: authenticated requests get server-resolved
  `user_id`, while anonymous bootstrap events are accepted without user data.
- Unknown fields and forbidden identifiers are rejected by Pydantic
  `extra="forbid"` schemas.
- Frontend-supplied `user_id`, Telegram ID, JWT, `initData`, full URLs, search
  text, checkout personal data, payment details, receipt paths/content, raw
  stack traces, and request/response bodies are not accepted.
- Migration `20260625_0036_add_privacy_safe_telemetry` adds nullable typed
  telemetry columns to `analytics_events`; existing analytics rows remain
  compatible.
- Raw telemetry retention defaults to 60 days and cleanup is batch-wise through
  `AnalyticsService.cleanup_telemetry(..., dry_run=True)` by default.

Frankfurt readiness adds `scripts/check_production_connectivity.py` for
read-only DNS/TCP/TLS/HTTP/cache/telemetry/Telegram checks. It accepts tokens
only through environment-variable names and redacts them from output.

See `../docs/ANALYTICS_TELEMETRY.md` for event names, allowlisted fields,
sampling defaults, ingestion limits, and local disable flags.

## Authentication settings

Telegram login validates Mini App `initData` with `TELEGRAM_WEBAPP_BOT_TOKEN` or
`TELEGRAM_BOT_TOKEN`, then returns a JWT access token. Set `JWT_SECRET_KEY` to a
strong local secret before using authenticated endpoints.

Seller Portal email/password auth is exposed under `/api/v1/seller-auth`.
Public registration creates a SELLER account only after Bot 2 verification:

- `POST /seller-auth/register/start`
- `POST /telegram/seller-bot/webhook` for Telegram Bot 2 webhook updates
- `POST /seller-auth/register/telegram-start` remains as the internal/manual
  service boundary used by the webhook flow
- `POST /seller-auth/register/confirm`
- `POST /seller-auth/login`
- `GET /seller-auth/me`

Use `TELEGRAM_BOT_TOKEN` for Bot 2. Set `TELEGRAM_SELLER_BOT_USERNAME` if the
API should return a direct `https://t.me/...` start link; otherwise the response
still includes the `/start seller_<token>` command. Set
`TELEGRAM_SELLER_WEBHOOK_SECRET` before exposing the webhook publicly. The
canonical webhook URL does not include the secret in the path; Telegram sends it
through the `X-Telegram-Bot-Api-Secret-Token` header configured by the webhook
setup script.
Verification codes and passwords are stored hashed, not in plain text.

Set and verify the production Bot 2 webhook without printing the bot token:

```bash
python scripts/set_seller_bot_webhook.py set --base-url https://api.stylexac.ru
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
In the seller group, use `/sellers` to find `Seller ID for commands`, then use
`/block_seller <Seller ID>` or `/unblock_seller <Seller ID>`. Do not use the
Telegram user id or chat id for these commands.

Customer Bot 1 notifications are exposed through:

- `POST /api/v1/telegram/customer-bot/webhook`
- `GET /api/v1/customer-notifications/me/subscription`
- `PATCH /api/v1/customer-notifications/me/subscription`
- `POST /api/v1/customer-notifications/me/start-link`
- `GET /api/v1/customer-notifications/subscriptions`
- `GET /api/v1/customer-notifications/service-deliveries`
- `GET/POST/PATCH /api/v1/customer-notifications/templates`
- `GET/POST/PATCH /api/v1/customer-notifications/campaigns`
- Campaign action endpoints:
  `/preview`, `/test`, `/schedule`, `/start`, `/pause`, `/cancel`,
  `/process-batch`, `/delivery-summary`, and `/deliveries`

Set `TELEGRAM_CUSTOMER_BOT_TOKEN`, `TELEGRAM_CUSTOMER_BOT_USERNAME`, and
`TELEGRAM_CUSTOMER_WEBHOOK_SECRET` for Bot 1. The webhook is protected only by
the Telegram `X-Telegram-Bot-Api-Secret-Token` header and uses the header-only
path, not a path secret. Bot 1 stores customer private chat state in
`CustomerTelegramSubscription`. Order service notifications and Phase 2
customer campaigns use `TELEGRAM_CUSTOMER_BOT_TOKEN` only; Bot 2
`TELEGRAM_BOT_TOKEN` remains for seller verification, seller chat operations,
and seller notifications.

Campaign MVP uses `NotificationTemplate`, `BroadcastCampaign`, and
`BroadcastDelivery`. It supports plain-text Telegram sends, safe audience
filters, materialized delivery rows, bounded manual/cron `process-batch`
processing, sanitized errors, and delivery reports. Recipient exports,
arbitrary database field interpolation, non-plain parse modes, and a separate
worker process are intentionally out of scope.

Set and verify the production Bot 1 webhook without printing the bot token:

```bash
python scripts/set_customer_bot_webhook.py set --base-url https://api.stylexac.ru
python scripts/set_customer_bot_webhook.py info
```
