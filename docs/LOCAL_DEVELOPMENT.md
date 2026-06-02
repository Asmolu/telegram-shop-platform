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
TELEGRAM_SELLER_BOT_USERNAME=<seller bot username without token>
TELEGRAM_SELLER_WEBHOOK_SECRET=<random local webhook secret>
JWT_SECRET_KEY=<local development secret>
```

`TELEGRAM_WEBAPP_BOT_TOKEN` is for Mini App auth. Seller verification,
notifications, and seller-chat broadcast use Bot 2 through `TELEGRAM_BOT_TOKEN`
and `TELEGRAM_SELLER_CHAT_ID`; the bot token is never exposed to the frontend.
`TELEGRAM_SELLER_BOT_USERNAME` only enables a direct `t.me` start link in the
Seller Panel. `TELEGRAM_SELLER_WEBHOOK_SECRET` protects the Bot 2 webhook
through Telegram's `X-Telegram-Bot-Api-Secret-Token` header. The legacy
path-secret webhook remains accepted for compatibility, but new webhook setup
uses the header-only path.

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

Seller registration uses the Bot 2 start-token flow. The Bot 2 webhook uses:

```text
POST /api/v1/telegram/seller-bot/webhook
```

Local Telegram webhook testing requires a public tunnel to the backend. Once the
tunnel URL is available, set Bot 2 webhook with:

```bash
cd backend
python scripts/set_seller_bot_webhook.py set --base-url https://your-public-tunnel.example
python scripts/set_seller_bot_webhook.py info
```

The older manual callback remains available for backend-only service tests:
`POST /api/v1/seller-auth/register/telegram-start`.

After `/start seller_<token>`, Bot 2 posts an approval request to
`TELEGRAM_SELLER_CHAT_ID`. Confirming the inline button sends the seller's
private verification code. Approval expires after 2 minutes and is enforced on
the next callback/resend/confirmation check, so a local worker is not required.
Seller group commands `/sellers`, `/block_seller <Seller ID>`, and
`/unblock_seller <Seller ID>` are rejected outside that configured chat.
`/sellers` labels the internal `Seller ID for commands`; do not use the
Telegram user id or chat id.

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
