# AGENTS.md — Telegram Shop Platform

These instructions are for Codex and other AI coding agents working in this repository.

## Project context

Telegram Shop Platform is a modular e-commerce system for a Telegram Mini App and Seller Panel.

The backend stack is now:

- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 async ORM
- Alembic migrations
- PostgreSQL
- Redis
- Local uploads with future S3/R2 compatibility

The frontend stack is:

- React
- Vite
- TypeScript

## Hard constraints

- Do not add NestJS back into the backend.
- Do not add Prisma back into the backend.
- Do not use Node.js as the backend runtime.
- Do not place business logic in FastAPI routers.
- Do not store files in PostgreSQL; store only file paths/URLs.
- Do not commit secrets, `.env`, tokens, private keys, uploaded user files, database dumps, or credentials.

## Backend architecture rules

Use the existing modular structure:

```text
backend/app/modules/<feature>/
├── router.py       # FastAPI endpoints only
├── schemas.py      # Pydantic request/response DTOs
├── service.py      # business logic
└── repository.py   # database access
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

## Domain rules

- PostgreSQL is the source of truth.
- Telegram is only an auth/notification/UI transport layer.
- `OrderItem` must be an immutable snapshot of the purchased product state.
- Order creation must be transactional.
- Stock deduction must happen atomically during checkout.
- Notifications must be emitted only after successful persistence.
- Reviews are allowed only after purchase and require moderation.
- Promo code usage must be tracked through `CouponUsage`.
- Critical seller/admin actions must create `AuditLog` entries.
- User behavior events should be captured through `AnalyticsEvent` when relevant.

## Frontend rules

- Keep both frontend apps on React + TypeScript.
- Use backend OpenAPI as the contract.
- Do not hardcode production API URLs.
- Use environment variables for API base URLs.
- Telegram Mini App should use Telegram SDK/webapp APIs only at the UI boundary.

## Required checks before finishing changes

Run relevant checks for the changed area.

Backend:

```bash
cd backend
python -m compileall app tests
ruff check .
pytest
```

Mini App:

```bash
cd mini-app
npm install
npm run build
```

Seller Panel:

```bash
cd seller-panel
npm install
npm run build
```

Docker smoke test when infrastructure changes:

```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

## Commit style

Use concise imperative commit messages:

- `Initialize FastAPI backend scaffold`
- `Add product catalog models`
- `Implement cart service`
- `Add order checkout transaction`
- `Configure GitHub CI`

## Documentation rules

Update documentation when changing architecture, commands, environment variables, or sprint scope:

- `README.md`
- `SRS.README.md`
- `SPRINT_PLAN.md`
- `docs/LOCAL_DEVELOPMENT.md`
- `docs/CODEX_WORKFLOW.md`

## UI / Frontend Design Source

When working on Mini App or Seller Portal UI, always read:

- `UI_DESIGN_SPEC.README.md`

Rules:

- Mini App and Seller Portal must not look identical.
- Mini App is mobile-first and marketplace-like.
- Seller Portal is desktop-first and dashboard-like.
- Backend tasks must not implement frontend UI unless the sprint explicitly asks for it.
