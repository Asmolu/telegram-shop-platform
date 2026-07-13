# Backend

FastAPI backend for StyleXac / TelegramShopPlatform.

## Stack

- Python 3.12+
- FastAPI
- Uvicorn
- SQLAlchemy 2.0 async ORM
- Alembic
- PostgreSQL 16
- Redis 7
- Pytest
- Ruff

## Production Context

| Area | Value |
| --- | --- |
| API domain | `https://api.stylexac.ru` |
| Production server | Aeza Frankfurt |
| Production path | `/opt/telegram-shop` |
| Production compose | `docker-compose.prod.yml` |
| Production env | `backend/.env.production` |
| Current migration head | `20260712_0054` |

## Module Structure

```text
backend/app/modules/<feature>/
├── router.py
├── schemas.py
├── service.py
└── repository.py
```

Rules:

- Routers parse requests, call services, and return responses.
- Services own business logic and transactions.
- Repositories own SQLAlchemy queries.
- SQLAlchemy models currently live in `backend/app/db/models.py`.
- Alembic migrations are required for schema changes.
- Async SQLAlchemy sessions are used.

## Current Modules

| Module | Purpose |
| --- | --- |
| `analytics` | Analytics events |
| `audit` | Seller/admin audit logs |
| `auth` | Telegram Mini App auth and JWT sessions |
| `banners` | Banner CRUD and public banners |
| `cart` | Cart items and totals |
| `categories` | Categories |
| `channel_entry` | Bot 1 channel publish/pin flow |
| `customer_notifications` | Bot 1 subscriptions, write access, service notifications, campaigns |
| `feed` | Mixed public feed of products and Looks |
| `favorites` | Favorite products |
| `idempotency` | Idempotent checkout support |
| `looks` | Look/outfit entities, images, product components, Look cart add |
| `manual_payments` | Manual payment settings, receipts, expiration |
| `notifications` | Seller/admin notification helpers |
| `orders` | Checkout, order snapshots, order status |
| `products` | Products, images, variants, search |
| `promo_codes` | Coupons and usage limits |
| `returns` | Return requests, attachments, lifecycle, refund/restock |
| `reviews` | Purchase-gated moderated reviews |
| `route_aliases` | Durable old slug resolution for products, categories, and Looks |
| `seller_auth` | Seller/admin auth |
| `seller_bot` | Bot 2 seller/admin flows |
| `statistics` | Dashboard statistics |
| `tags` | Tags |
| `telegram` | Bot webhook routing |
| `uploads` | Local upload validation and storage |
| `users` | Users and roles |

## Environment

Local checks use `backend/.env`. Production/VDS work uses `backend/.env.production`.

Do not commit real secrets. Use placeholders in docs:

```text
<SECRET>
<BOT_TOKEN>
<DATABASE_URL>
<JWT_SECRET>
```

## Auth

- Mini App login uses Telegram `initData`.
- Backend validates signature and `auth_date` server-side.
- Backend upserts the Telegram user and issues JWT.
- Raw `initData` must not be stored or logged.
- Roles are `USER`, `SELLER`, `ADMIN`.

## Orders and Checkout

- Checkout is transactional.
- Stock is checked and decremented in checkout.
- `OrderItem` stores immutable purchased-product snapshots.
- Coupon usage is tracked through `CouponUsage`.
- Notifications are emitted after successful persistence.

## Customer Notifications

Bot 1 owns:

- customer `/start`
- customer `/stop`
- service notifications
- customer campaigns
- channel entry publish/pin

Bot 2 owns seller/admin/auth-related flows.

Mini App write access is persisted through:

```text
POST /api/v1/customer-notifications/me/write-access
```

Write access enables service notifications without enabling marketing. Campaign delivery requires real private Bot 1 chat state.

## Uploads

Uploads support products, banners, categories, tags, reviews, customer campaigns, manual payment receipts, and temporary files. PostgreSQL stores paths/URLs only.

Current banner crop profiles:

- horizontal native banner: `400:207`
- vertical: `9:16`
- popup: `3:4`
- aggressive popup: `9:16`

## Local Checks

```bash
python -m compileall app tests
ruff check .
pytest
```

Strict warning mode:

```bash
pytest -W error
```

Focused checks:

```bash
pytest tests/test_migrations.py tests/test_channel_entry.py tests/test_customer_notifications.py
```

## Migrations

```bash
alembic upgrade head
alembic current
```

Current production head:

```text
20260703_0047
```

## Production Deploy Reference

See:

- `../docs/PRODUCTION_DEPLOYMENT.md`
- `../docs/OPERATIONS.md`
- `../docs/ENVIRONMENT.md`

## Transactional Outbox

The backend atomically stores order/manual-payment domain events and processes them from the
FastAPI lifespan. Configure with the `OUTBOX_*` variables in `.env.example`. Run
`pytest tests/test_outbox.py -W error`; use a disposable `TEST_POSTGRES_URL` for the real
concurrency test. Migrations through `20260712_0054` must be applied before the new backend starts.
