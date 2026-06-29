# Local Development

This guide covers local development for StyleXac.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `backend/` | FastAPI backend, Alembic migrations, tests |
| `mini-app/` | Customer Telegram Mini App |
| `seller-panel/` | Seller/admin dashboard |
| `docs/` | Operational and architecture documentation |
| `deploy/` | Deployment and reverse-proxy support files if present |
| `docker-compose.yml` | Local compose stack when used |
| `docker-compose.prod.yml` | Production compose stack |

## Environment Files

| File | Use |
| --- | --- |
| `backend/.env` | Local backend development and checks |
| `backend/.env.production` | VDS/server work and production-domain checks only |
| `mini-app/.env.local` | Optional local Mini App overrides |
| `seller-panel/.env.local` | Optional local Seller Panel overrides |

Never copy real production secrets into local docs, screenshots, or commits.

## Backend Setup

Backend stack:

- Python 3.12+
- FastAPI
- SQLAlchemy 2.0 async ORM
- Alembic
- PostgreSQL 16
- Redis 7
- Pytest
- Ruff

Typical local commands:

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[dev]"
python -m compileall app tests
ruff check .
pytest
```

On Windows PowerShell, activate the venv with:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
```

Run migrations against the configured local database:

```bash
cd backend
alembic upgrade head
alembic current
```

If the host lacks Python, Ruff, or Pytest, run backend checks in the backend Docker container.

## Mini App Setup

```bash
cd mini-app
npm install
npm test -- --run
npm run build
npm run verify:bundle
```

The Mini App uses Telegram WebApp APIs only at the UI boundary. For browser development outside Telegram, the app must handle missing `Telegram.WebApp` gracefully.

Important implemented behavior:

- waits for `Telegram.WebApp.initData` before login
- deduplicates in-flight Telegram login
- coordinates API `401` refresh with one retry
- supports feed, category, search, product detail, cart, profile, and checkout
- uses a draggable help widget on feed/category/search
- persists write-access results only after user action

## Seller Panel Setup

```bash
cd seller-panel
npm install
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

Implemented areas include product management, variants, uploads, banners, promo codes, customer notifications, channel entry publishing, and seller/admin auth-related flows.

## Local API URLs

Use environment variables:

```text
VITE_API_BASE_URL=/api/v1
```

For direct local backend access:

```text
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

Do not hardcode `https://api.stylexac.ru` in frontend source.

## Backend Architecture Rules

- Keep business logic out of routers.
- Put business rules and transactions in services.
- Put SQLAlchemy queries in repositories.
- Keep SQLAlchemy models in `backend/app/db/models.py` until a deliberate model-layer split is made.
- Add Alembic migrations for schema changes.
- Use async SQLAlchemy sessions.
- PostgreSQL is the source of truth.
- Redis is used only for cache, rate limiting, and temporary state where implemented.

## Useful Local Checks

```bash
git diff --check
```

Documentation consistency searches:

```bash
rg -n "tsplatform\.ru|mini\.tsplatform\.ru|api\.tsplatform\.ru|seller\.tsplatform\.ru" .
rg -n "20260628_0039" .
```

`20260628_0039` is expected in current production docs. Older ids should appear only as clearly historical notes.
