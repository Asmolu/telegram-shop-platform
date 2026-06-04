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
| Native Mini App banner | 16:9 | 1600x900 | 800x450 | 2400x1350 |
| Aggressive promo banner | 3:1 | 1800x600 | 900x300 | 2400x800 |

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

Sprint 11 adds backend-only observability modules:

- `backend/app/modules/analytics/` records user behavior events and exposes seller/admin reporting.
- `backend/app/modules/audit/` records seller/admin actions on critical entities.

Seller/admin endpoints are available under the canonical API prefix:

- `GET /api/v1/analytics/events`
- `GET /api/v1/analytics/summary`
- `GET /api/v1/audit-logs`
- `GET /api/v1/audit-logs/{log_id}`

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

Set the production webhook with:

```bash
cd backend
python scripts/set_seller_bot_webhook.py set --base-url https://api.tsplatform.ru
python scripts/set_seller_bot_webhook.py info
```

## Customer Bot 1 notification registry

Customer notification MVP Phase 1 adds a Bot 1 subscription registry without
campaign sending. Bot 1 remains separate from Bot 2 seller registration and
uses:

- `POST /api/v1/telegram/customer-bot/webhook`, protected by
  `X-Telegram-Bot-Api-Secret-Token` matching `TELEGRAM_CUSTOMER_WEBHOOK_SECRET`
- `GET /api/v1/customer-notifications/me/subscription`
- `PATCH /api/v1/customer-notifications/me/subscription`
- `POST /api/v1/customer-notifications/me/start-link`
- `GET /api/v1/customer-notifications/subscriptions` for SELLER/ADMIN recipient
  status listing

Bot 1 stores private chat availability in `CustomerTelegramSubscription`.
`telegram_user_id` and `telegram_chat_id` are stored separately; Mini App auth
still validates Telegram `initData` without persisting the raw payload. The
Mini App Profile shows Telegram notification settings, and Seller Panel has a
Customer Notifications recipient list. Marketing campaigns, campaign delivery
tables, and mass sends are intentionally out of scope for this phase.

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
- `docs/BACKUP_AND_RESTORE.md`
- `docs/SECURITY_REVIEW.md`

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
