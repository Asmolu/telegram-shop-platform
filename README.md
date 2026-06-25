# Telegram Shop Platform

Telegram Shop Platform is a modular e-commerce system for a clothing shop built around a Telegram Mini App and a Seller Panel.

The repository is intentionally prepared as a **Python/FastAPI modular monolith** backend with separate frontend applications.

## Current status

This is a project scaffold and architecture baseline, not a completed product. The repository is prepared for iterative development with Codex through Git.

## Stack

| Layer          | Technology                          |
| -------------- | ----------------------------------- |
| Customer app   | React + Vite + TypeScript           |
| Seller panel   | React + Vite + TypeScript           |
| Backend API    | Python 3.12 + FastAPI               |
| ORM            | SQLAlchemy 2.0 async                |
| Migrations     | Alembic                             |
| Database       | PostgreSQL                          |
| Cache / queues | Redis                               |
| Files          | Local `/uploads`, cloud-ready later |
| API contract   | OpenAPI                             |
| Auth           | Telegram initData validation + JWT  |

## Image upload standards

Seller-uploaded product and banner images are validated on the backend after decoding the file.
The Seller Panel crops images before upload to match these display-safe standards:

| Surface | Aspect ratio | Recommended | Minimum | Maximum accepted |
| ------- | ------------ | ----------- | ------- | ---------------- |
| Product card image | 4:5 | 1200x1500 | 600x750 | 1600x2000 |
| Product detail/gallery image | 4:5 | 1200x1500 | 600x750 | 1600x2000 |
| Category/tag card image | 4:3 | 1200x900 | 600x450 | 1600x1200 |
| Horizontal Mini App banner | 400:207 | 2000x1035 | 1200x621 | 2400x1242 |
| Vertical Mini App banner | 9:16 | 900x1600 | 450x800 | 1350x2400 |
| Popup banner | 3:4 | 900x1200 | 450x600 | 1350x1800 |
| Aggressive popup banner | 9:16 | 900x1600 | 450x800 | 1350x2400 |

Backend uploads keep the existing extension, MIME, and 5 MB file-size checks and also reject
images that are too small, too large, or outside the expected aspect-ratio tolerance.

## Repository structure

```text
.
├── backend/              # FastAPI backend
├── mini-app/             # Telegram Mini App frontend
├── seller-panel/         # Seller/Admin frontend
├── docs/                 # Development documentation
├── .github/              # GitHub workflows and templates
├── AGENTS.md             # Instructions for Codex / AI coding agents
├── SRS.README.md         # Software Requirements Specification
├── SPRINT_PLAN.md        # Sprint-based implementation plan
└── docker-compose.yml    # Local dev infrastructure
```

## Backend architecture

```text
backend/app/
├── api/                  # API router composition
├── common/               # shared dependencies and helpers
├── core/                 # config, security, exception handling
├── db/                   # SQLAlchemy base, session, models
├── events/               # event names / event contract
├── jobs/                 # background job placeholders
└── modules/              # feature modules
    ├── auth/
    ├── users/
    ├── products/
    ├── categories/
    ├── tags/
    ├── banners/
    ├── promo_codes/
    ├── cart/
    ├── orders/
    ├── reviews/
    ├── favorites/
    ├── notifications/
    ├── uploads/
    ├── telegram/
    └── statistics/
```

## Local start with Docker

Create a local backend env file:

```bash
cp backend/.env.example backend/.env
```

Start services:

```bash
docker compose up -d --build
```

Apply migrations:

```bash
docker compose exec backend alembic upgrade head
```

Check backend health:

```bash
curl http://localhost:8000/health
```

Open API docs:

```text
http://localhost:8000/docs
http://localhost:8000/api/v1/openapi.json
```

## Backend observability API

Mini App privacy-safe telemetry is ingested through
`POST /api/v1/analytics/telemetry` and stored in the existing
`analytics_events` table with schema-versioned, allowlisted fields only. It is
used for startup timing, API latency/retry/error correlation, Web Vitals, chunk
load recovery, and ambiguous checkout/payment/receipt outcomes. Telemetry does
not accept Telegram `initData`, JWTs, search text, checkout personal data,
receipt paths/content, full URLs, raw stack traces, raw user agents, or
frontend-supplied user identifiers. See
`docs/ANALYTICS_TELEMETRY.md` for the event schema, sampling defaults,
retention policy, and local disable flags.

Sprint 11 adds backend-only observability modules:

- `backend/app/modules/analytics/` records user behavior events and exposes seller/admin reporting.
- `backend/app/modules/audit/` records seller/admin actions on critical entities.

Seller/admin endpoints are available under the canonical API prefix:

- `GET /api/v1/analytics/events`
- `GET /api/v1/analytics/summary`
- `GET /api/v1/audit-logs`
- `GET /api/v1/audit-logs/{log_id}`

## Mini App network resilience

The Mini App uses one shared API request layer. It classifies auth, validation,
network, timeout, aborted, rate-limit, temporary server, and permanent server
errors without logging JWTs, Telegram `initData`, or personal payload data.
Backend `X-Request-ID` is preserved in normalized errors for support.

Automatic retry is limited to safe idempotent GET reads: catalog, categories,
tags, banners, product details/reviews, favorites, cart, orders, payment status,
profile, personal data, and customer notification subscription. Retries use up
to 3 attempts with exponential backoff, jitter, `Retry-After`, and only for
network errors, timeout, HTTP 408, 429, 502, 503, and 504. Mutations are never
retried automatically.

Checkout, manual payment submit, and receipt upload accept an optional
`Idempotency-Key` header. New Mini App clients send a stable key per user action
and reuse it for manual retry after temporary failures. Old clients without the
header remain compatible and keep the existing transactional behavior.

## Product search foundation

Product search uses PostgreSQL `pg_trgm` through Alembic-managed `CREATE EXTENSION IF NOT EXISTS
pg_trgm`. Public product list responses use a compact card DTO with display prices, badge fields,
card image URLs, availability, and compact active variants. Search tuning fields such as
`search_priority` and `search_aliases` stay in seller/admin workflows and are not sent to Mini App
card lists. Lower numeric `search_priority` values rank first in matching search results; the
default is `2`.

Catalog products own a `size_grid`: active grids are `clothing_alpha` and `shoes_eu`.
The legacy `shoes_ru` value remains only for historical products/order snapshots and must not be
used for new footwear. Clothing variants support `XS`, `S`, `M`, `L`, `XL`, `XXL`, `3XL`, and
`ONE_SIZE`. Footwear variants use explicit EU whole sizes `35` through `46`; prefixes such as
RU/EU/US/UK and half sizes are rejected. Public product listing supports server-side `size_grid`,
`size`, and `color` filters against active variants. General search matches exact numeric variant
sizes and expands common Russian color words and conservative typos to the Latin color values stored
on variants.

Public catalog endpoints support safe conditional requests. Products, product detail, and banners
return `ETag` with revalidation; categories and tags use short public caching. Personalized state
such as cart and favorites is private/no-store.

## Seller Portal auth and bot management

Seller Portal now supports email/password auth through `/api/v1/seller-auth`.
Registration uses Bot 2, configured with `TELEGRAM_BOT_TOKEN`, and a start-token
flow:

1. `POST /api/v1/seller-auth/register/start` creates a pending seller registration.
2. The seller opens Bot 2 with `/start seller_<token>`.
3. Telegram delivers the Bot 2 update to
   `POST /api/v1/telegram/seller-bot/webhook`, protected by the
   `X-Telegram-Bot-Api-Secret-Token` header matching
   `TELEGRAM_SELLER_WEBHOOK_SECRET`.
4. The backend links the Telegram user/chat through the existing seller
   registration service boundary.
5. Bot 2 sends an approval request to `TELEGRAM_SELLER_CHAT_ID` with safe seller
   details and Confirm / Reject inline buttons.
6. Approval must happen within 2 minutes. Expiration is enforced on the next
   registration action or callback, so no separate worker is required for the
   MVP.
7. After group approval, Bot 2 sends a verification code, and the seller confirms through
   `POST /api/v1/seller-auth/register/confirm`.

Seller bot management is available under `/api/v1/seller-bot` for SELLER/ADMIN
users. MVP broadcast sends only to the configured seller notification chat; it
does not claim all-user Telegram broadcast unless a recipient registry is added.
In the seller group, Bot 2 also supports `/sellers`,
`/block_seller <Seller ID>`, and `/unblock_seller <Seller ID>` for seller
visibility and safe deactivation. `/sellers` shows `Seller ID for commands`;
use that internal ID, not the Telegram user id or chat id.
`/active_orders` returns up to ten non-final orders with Russian status labels,
customer, delivery, item snapshots, totals, and Seller Panel links.

Bot 2 product creation uses one strict, stateless photo-caption flow. Send one
photo with `/new_product`, Russian field labels, `Тип размеров: одежда` or
`Тип размеров: обувь`, and one variant per line in the form
`размер / цвет / остаток / SKU`. SKU may be blank and receives a safe generated
value. Categories and tags must already exist; Bot 2 never creates or silently
ignores taxonomy. Products default to `DRAFT` and the reply includes the Seller
Panel edit link. `/new_product_help` returns complete clothing and footwear
examples. Clothing accepts `XS`, `S`, `M`, `L`, `XL`, `XXL`, `3XL`, and
`ONE_SIZE`; footwear creates `shoes_eu` products and accepts only plain EU whole-size strings
`35` through `46`, without RU/EU/US/UK prefixes or half sizes. Existing `shoes_ru` rows are rendered
as legacy RU data rather than being converted in place.

Set the production webhook with:

```bash
cd backend
python scripts/set_seller_bot_webhook.py set --base-url https://api.stylexac.ru
python scripts/set_seller_bot_webhook.py info
```

## Customer Bot 1 notifications and campaigns

Customer notification MVP Phase 1 adds a Bot 1 subscription registry. Phase 1.5
adds order-related customer service notifications through Bot 1. Phase 2 adds
controlled templates, campaigns, materialized delivery rows, bounded grouped
processing, and reports. Bot 1 remains separate from Bot 2 seller registration
and uses:

- `POST /api/v1/telegram/customer-bot/webhook`, protected by
  `X-Telegram-Bot-Api-Secret-Token` matching `TELEGRAM_CUSTOMER_WEBHOOK_SECRET`
- `GET /api/v1/customer-notifications/me/subscription`
- `PATCH /api/v1/customer-notifications/me/subscription`
- `POST /api/v1/customer-notifications/me/start-link`
- `GET /api/v1/customer-notifications/subscriptions` for SELLER/ADMIN recipient
  status listing
- `GET /api/v1/customer-notifications/service-deliveries` for SELLER/ADMIN
  read-only service delivery attempt listing
- `POST /api/v1/orders/admin/{order_id}/customer-message` for SELLER/ADMIN
  text and/or JPEG, PNG, or WebP delivery to the order customer through Bot 1
- `GET/POST/PATCH /api/v1/customer-notifications/templates` for SELLER/ADMIN
  template management
- `GET/POST/PATCH /api/v1/customer-notifications/campaigns` plus
  `/preview`, `/test`, `/schedule`, `/start`, `/pause`, `/cancel`,
  `/process-batch`, `/delivery-summary`, and `/deliveries` for controlled
  campaign operations and reporting

Bot 1 stores private chat availability in `CustomerTelegramSubscription`.
`telegram_user_id` and `telegram_chat_id` are stored separately; Mini App auth
still validates Telegram `initData` without persisting the raw payload. The
Mini App Profile shows Telegram notification settings, and Seller Panel has a
Customer Notifications area for recipients, templates, campaigns, and delivery
reports. Order service notifications and campaign sends use
`TELEGRAM_CUSTOMER_BOT_TOKEN`; customer campaigns must not use
`TELEGRAM_BOT_TOKEN` or `TELEGRAM_WEBAPP_BOT_TOKEN`.
Seller-to-customer order messages use the same Bot 1 subscription and delivery
audit path. Images are validated up to 5 MB and sent directly to Telegram
without storing a second uploaded copy.

Phase 2 deliberately keeps recipient exports, arbitrary database field
interpolation, non-plain Telegram parse modes, and a separate worker process out
of scope. The backend lifespan worker automatically processes due campaigns in
small groups when `TELEGRAM_CUSTOMER_BOT_TOKEN` is configured. The protected
`/process-batch` endpoint remains available for controlled recovery and support.
Preview and test-send are recommended checks, but are not hidden activation
requirements. A delivery marked sent means Telegram Bot API accepted the Bot 1
send; it is not a read receipt. Staging tests should start with one internal
account that has opened Bot 1 with `/start`, then enable a tiny campaign before
production use.

## Manual SBP payments

Checkout uses a manual 100% SBP transfer workflow. A seller or administrator
must first enable `Ручная оплата через СБП` in Seller Panel settings and provide
a Russian phone number. New orders snapshot the normalized phone, display
phone, bank, recipient, amount, and transfer comment for a 30-minute reservation;
later settings changes do not alter existing payments.

Customers can upload a JPEG, PNG, or WebP receipt up to 5 MB and submit payment
for review. Receipts are stored under `backend/uploads/payment_receipts/` (or
`/app/uploads/payment_receipts/` in Compose). Bot 2 posts seller-group review
buttons when configured; Bot 1 is used only for optional customer payment
notifications. The backend lifespan expiration worker is controlled by
`MANUAL_PAYMENT_EXPIRATION_WORKER_ENABLED` and
`MANUAL_PAYMENT_EXPIRATION_POLL_SECONDS`.
The Bot 2 review message chat/message IDs are stored on the manual payment.
Seller Panel and Bot 2 approve/reject actions edit that message to remove stale
buttons and show the final result; if editing fails, Bot 2 sends a follow-up.

## Production hardening

Sprint 14 adds MVP production readiness:

- Redis caching for public catalog, taxonomy, active banners, and approved product reviews.
- Configurable rate limiting for global API traffic plus stricter login, upload, checkout, promo validation, and review creation limits.
- Structured JSON request logging with request IDs and duration.
- Error monitoring placeholders through `ERROR_MONITORING_ENABLED` and `SENTRY_DSN`.
- A production Docker Compose profile in `docker-compose.prod.yml`.
- Backup and restore guidance for PostgreSQL and uploads.
- Security review documentation and production env examples.

Production/staging docs:

- `docs/PRODUCTION_DEPLOYMENT.md`
- `docs/FRANKFURT_DEPLOYMENT_READINESS.md`
- `docs/BACKUP_AND_RESTORE.md`
- `docs/SECURITY_REVIEW.md`

Frankfurt deployment readiness includes the same-origin Caddy routing template
in `deploy/caddy/Caddyfile.frankfurt.example`, synthetic connectivity checks,
Telegram egress preflight, webhook cutover order, ADMIN bootstrap steps, and
backup readiness. It is documentation only; production deployment, DNS,
webhooks, BotFather changes, and secret rotation remain manual operations.

## Local backend without Docker

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

For Linux/macOS:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend development

Mini App:

```bash
cd mini-app
npm install
npm run dev
```

Seller Panel:

```bash
cd seller-panel
npm install
npm run dev
```

## Quality checks

Backend:

```bash
cd backend
ruff check .
pytest
python -m compileall app tests
```

Frontend:

```bash
cd mini-app
npm run build

cd ../seller-panel
npm run build
```

## Important rules

- Do not reintroduce NestJS or Prisma into the backend.
- SQLAlchemy models and Alembic migrations are the database source of truth.
- Routers must stay thin; business logic belongs in services.
- Repositories own database queries.
- Telegram is a UI/transport layer, not the source of system data.
- Order data must be persisted in PostgreSQL before notifications are emitted.
- Never commit `.env`, tokens, private keys, uploaded user files, or database dumps.

See `AGENTS.md` before giving tasks to Codex.

## Project Documentation

- `SRS.README.md` — product/system requirements.
- `SPRINT_PLAN.md` — implementation roadmap.
- `AGENTS.md` — Codex/agent development rules.
- `UI_DESIGN_SPEC.README.md` — Mini App and Seller Portal UI specification.
