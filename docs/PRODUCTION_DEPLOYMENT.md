# Production Deployment

Sprint 14 adds a small Docker Compose production profile for MVP staging or single-node production.

## Required files

Create these files from examples and replace every placeholder before starting services:

```bash
cp backend/.env.production.example backend/.env.production
cp mini-app/.env.production.example mini-app/.env.production
cp seller-panel/.env.production.example seller-panel/.env.production
```

Do not commit the generated `.env.production` files.

## Required environment

Backend:

- `APP_ENV=production`
- `DEBUG=false`
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET_KEY`
- `CORS_ORIGINS`
- `TELEGRAM_WEBAPP_BOT_TOKEN`
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_SELLER_CHAT_ID` for Bot 2 seller verification,
  seller notifications, and seller-chat broadcast
- `TELEGRAM_SELLER_BOT_USERNAME` if the Seller Panel should show a direct `t.me`
  start link during registration
- cache and rate limit settings from `backend/.env.production.example`

Frontend:

- `VITE_API_BASE_URL` for both `mini-app` and `seller-panel`
- `VITE_TELEGRAM_BOT_USERNAME` for Mini App UI links only, not bot tokens

## Start

Validate the compose file syntax:

```bash
docker compose -f docker-compose.prod.yml config
```

Build and start:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml up -d --build
```

Run migrations:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend alembic upgrade head
```

Seller Portal email/password auth requires migration
`20260601_0013_add_seller_auth_tables.py`. Bot 2 must be connected by webhook
or polling to the seller registration start-token service boundary; until then,
`POST /api/v1/seller-auth/register/telegram-start` is the documented manual
callback simulation endpoint.

Smoke checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/products
curl http://localhost:8000/api/v1/categories
curl http://localhost:8000/api/v1/tags
```

## Services

- Backend API: `http://localhost:8000`
- Seller Panel: `http://localhost:8080`
- Mini App static bundle: `http://localhost:8081`
- PostgreSQL: private compose network, persistent `postgres_prod_data` volume
- Redis: private compose network, persistent `redis_prod_data` volume
- Uploads: persistent `uploads_data` volume mounted at `/app/uploads`

## Migrations

- Add new Alembic migrations for schema changes.
- Do not edit old migrations after they have been shared.
- Review generated migrations before running them in staging or production.
- Run `alembic upgrade head` during deployment before routing traffic to a new backend build.
- Keep downgrade functions when the existing migration style supports them.

## Observability

Application logs are JSON by default and include request id, method, path, status, and duration.
Error monitoring is prepared through `ERROR_MONITORING_ENABLED` and `SENTRY_DSN`, but no external SDK is required for MVP.

## Known MVP Limits

- Compose is intended for MVP staging or a single-node deployment, not high availability.
- Public review and seller moderation lists keep their current response shape; review admin pagination is documented as a later compatibility-safe improvement.
- Redis is a cache and rate-limit accelerator. Public endpoints fall back to PostgreSQL if Redis is unavailable.
