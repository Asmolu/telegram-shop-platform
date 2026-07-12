# AGENTS.md - Telegram Shop Platform / StyleXac

These instructions are for Codex and other AI coding agents working in this repository.

## Project Context

StyleXac is a modular e-commerce system for a Telegram Mini App and Seller Panel.

Production context:

| Area | Current value |
| --- | --- |
| Main domain and Mini App entry | `https://stylexac.ru` |
| Mini App direct domain | `https://mini.stylexac.ru` |
| API domain | `https://api.stylexac.ru` |
| Seller Panel domain | `https://seller.stylexac.ru` |
| Server | Aeza Frankfurt |
| SSH alias | `tsplatform-frankfurt` |
| Production path | `/opt/telegram-shop` |
| Production compose file | `docker-compose.prod.yml` |
| Production env file | `backend/.env.production` |
| Current migration head | `20260712_0054` |

Backend stack:

- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 async ORM
- Alembic
- PostgreSQL 16
- Redis 7
- Local uploads with future S3/R2 compatibility
- Uvicorn
- Pytest
- Ruff

Frontend stack:

- React
- Vite
- TypeScript

Bots:

- Bot 1 is customer-facing.
- Bot 2 is for seller/admin/auth-related flows.

## Hard Constraints

- Do not add NestJS back into the backend.
- Do not add Prisma back into the backend.
- Do not use Node.js as the backend runtime.
- Do not place business logic in FastAPI routers.
- Do not store files in PostgreSQL; store only file paths/URLs.
- Do not commit secrets, `.env`, `.env.production`, tokens, private keys, uploaded user files, database dumps, or credentials.
- Do not expose bot tokens, DB passwords, JWT secrets, Yandex Disk tokens, or private production credentials in docs or reports.
- Do not mix Bot 1 and Bot 2 responsibilities.

## Backend Architecture Rules

Use the existing modular structure:

```text
backend/app/modules/<feature>/
├── router.py
├── schemas.py
├── service.py
└── repository.py
```

Rules:

- Routers parse requests, call services, and return responses.
- Services own business rules and transactions.
- Repositories own SQLAlchemy queries.
- SQLAlchemy models live in `backend/app/db/models.py` until the model layer becomes too large.
- Alembic migrations are required for database schema changes.
- Use async SQLAlchemy sessions.
- Prefer explicit domain-specific methods over generic catch-all helpers.
- Keep module boundaries clear.

## Domain Rules

- PostgreSQL is the source of truth.
- Redis is used for cache, rate limiting, and temporary state where implemented.
- Telegram is only an auth, notification, and UI transport layer.
- Telegram Mini App `initData` must always be validated server-side.
- Raw `initData` must not be logged or stored.
- `OrderItem` must be an immutable snapshot of the purchased product state.
- Order creation must be transactional.
- Stock deduction must happen atomically during checkout.
- Notifications must be emitted only after successful persistence.
- Reviews are allowed only after purchase and require moderation.
- Promo code usage must be tracked through `CouponUsage`.
- Critical seller/admin actions must create `AuditLog` entries.
- User behavior events should be captured through `AnalyticsEvent` when relevant.

## Customer Notification Rules

- Bot 1 owns customer `/start`, `/stop`, service notifications, campaigns, and channel entry publish/pin.
- Bot 2 owns seller/admin/auth-related flows.
- Bot 1 `/start` creates or updates real private chat subscription state.
- Bot 1 `/stop` disables notification eligibility according to current backend behavior.
- Mini App write access must be requested only after a user action.
- `POST /api/v1/customer-notifications/me/write-access` persists write-access state.
- Write access enables service notifications and does not silently enable marketing.
- Service sends prefer real private-chat `telegram_chat_id`.
- If no real private chat exists, current service notification logic can use `telegram_user_id` when `write_access_granted=true`.
- Campaign delivery requires a real private Bot 1 chat and eligible opt-in state.

## Channel Entry Rules

- Seller Panel route is `/channel-entry`.
- Bot 1 publishes and optionally pins the channel message.
- Channel buttons use URL links to Mini App `startapp`, not Telegram `web_app` buttons.
- Default channel entry start parameter is `channel_pin`.
- Channel-entry `initData` auth can create or update a `User`, but does not create real private Bot 1 chat state.

## Frontend Rules

- Keep both frontend apps on React + TypeScript.
- Use backend OpenAPI as the contract.
- Do not hardcode production API URLs.
- Use environment variables for API base URLs.
- Telegram Mini App should use Telegram SDK/WebApp APIs only at the UI boundary.

## UI / Frontend Design Source

When working on Mini App or Seller Panel UI, always read:

- `UI_DESIGN_SPEC.README.md`

Rules:

- Mini App and Seller Portal must not look identical.
- Mini App is mobile-first and marketplace-like.
- Seller Portal is desktop-first and dashboard-like.
- Backend tasks must not implement frontend UI unless the sprint explicitly asks for it.

## Required Checks Before Finishing Changes

Run relevant checks for the changed area.

Backend:

```bash
cd backend
python -m compileall app tests
ruff check .
pytest
```

Backend strict warning mode:

```bash
cd backend
pytest -W error
```

Mini App:

```bash
cd mini-app
npm test -- --run
npm run build
npm run verify:bundle
```

Seller Panel:

```bash
cd seller-panel
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

Repository:

```bash
git diff --check
```

Docker smoke test when infrastructure changes:

```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

## Production Operations

Deploy from the production host:

```bash
ssh tsplatform-frankfurt
cd /opt/telegram-shop
git status --short
git fetch origin
git pull --ff-only origin main
docker compose --env-file backend/.env.production -f docker-compose.prod.yml config >/tmp/telegram-shop-compose-check.yml
sudo systemctl start telegram-shop-backup.service
docker compose --env-file backend/.env.production -f docker-compose.prod.yml build backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic upgrade head
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic current
docker compose --env-file backend/.env.production -f docker-compose.prod.yml up -d backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
```

Production backup must use:

```bash
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
```

## Documentation Rules

Update documentation when changing architecture, commands, environment variables, production operations, domains, bot responsibilities, or sprint scope.

Key docs:

- `README.md`
- `SRS.README.md`
- `SPRINT_PLAN.md`
- `UI_DESIGN_SPEC.README.md`
- `docs/ARCHITECTURE.md`
- `docs/ENVIRONMENT.md`
- `docs/PRODUCTION_DEPLOYMENT.md`
- `docs/CUSTOMER_NOTIFICATIONS_ARCHITECTURE.md`
- `docs/TELEGRAM_CHANNEL_ENTRY.md`
- `docs/TESTING.md`
- `docs/OPERATIONS.md`
- `docs/LOCAL_DEVELOPMENT.md`
- `docs/CODEX_WORKFLOW.md`
