# Local Development

## Requirements

- Git
- Docker Desktop
- Python 3.12+
- Node.js 20+
- npm

## Start infrastructure

From repository root:

```bash
cp backend/.env.example backend/.env
```

Windows PowerShell:

```powershell
Copy-Item backend/.env.example backend/.env
```

Start Docker services:

```bash
docker compose up -d --build
```

Check containers:

```bash
docker compose ps
```

Apply migrations:

```bash
docker compose exec backend alembic upgrade head
```

Check backend:

```bash
curl http://localhost:8000/health
```

## Backend development without Docker backend container

You can still use Docker for PostgreSQL and Redis, but run FastAPI locally.

1. Start database services:

```bash
docker compose up -d postgres redis
```

2. Create env file for local host access. In `backend/.env`, use:

```text
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/telegram_shop
REDIS_URL=redis://localhost:6379/0
TELEGRAM_WEBAPP_BOT_TOKEN=<your bot token>
TELEGRAM_BOT_TOKEN=<seller notification bot token>
TELEGRAM_SELLER_CHAT_ID=<seller group or chat id>
JWT_SECRET_KEY=<local development secret>
```

`TELEGRAM_WEBAPP_BOT_TOKEN` is for Mini App auth. Seller notifications are sent
with `TELEGRAM_BOT_TOKEN` to `TELEGRAM_SELLER_CHAT_ID`.

3. Run backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Sprint 14 adds Redis-backed caching and rate limiting. Local development can keep the defaults from
`backend/.env.example`; if Redis is stopped, public catalog reads still work and rate limiting uses
the isolated in-memory fallback.

Useful local toggles:

```text
CACHE_ENABLED=true
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REDIS_ENABLED=true
RATE_LIMIT_IN_MEMORY_FALLBACK_ENABLED=true
LOG_FORMAT=json
ERROR_MONITORING_ENABLED=false
```

## Mini App

```bash
cd mini-app
npm install
npm run dev
```

Default URL:

```text
http://localhost:5173
```

## Seller Panel

```bash
cd seller-panel
npm install
npm run dev
```

Default URL:

```text
http://localhost:5174
```

## API documentation

```text
http://localhost:8000/docs
http://localhost:8000/api/v1/openapi.json
```

## Production profile docs

Production/staging deployment, backups, and security review are documented in:

- `docs/PRODUCTION_DEPLOYMENT.md`
- `docs/BACKUP_AND_RESTORE.md`
- `docs/SECURITY_REVIEW.md`
