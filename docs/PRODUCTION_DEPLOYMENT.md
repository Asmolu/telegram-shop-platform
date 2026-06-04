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
- `TELEGRAM_SELLER_WEBHOOK_SECRET` for the protected Bot 2 webhook
  `X-Telegram-Bot-Api-Secret-Token` header
- `TELEGRAM_CUSTOMER_BOT_TOKEN` for Bot 1 customer notification registry
  webhook setup and future customer-facing notification delivery
- `TELEGRAM_CUSTOMER_BOT_USERNAME` for Mini App customer notification start
  links
- `TELEGRAM_CUSTOMER_WEBHOOK_SECRET` for the protected Bot 1 webhook
  `X-Telegram-Bot-Api-Secret-Token` header
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

Seller Portal email/password auth, seller approval, and Customer Notifications
MVP Phase 1 require migrations through head `20260604_0016`. Bot 2 is connected
through:

```text
POST /api/v1/telegram/seller-bot/webhook
```

Set the webhook after deployment:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/set_seller_bot_webhook.py set --base-url https://api.tsplatform.ru
```

Verify Telegram webhook state without printing the bot token:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/set_seller_bot_webhook.py info
```

The webhook URL should be:

```text
https://api.tsplatform.ru/api/v1/telegram/seller-bot/webhook
```

Bot 1 customer notification registry is connected through:

```text
POST /api/v1/telegram/customer-bot/webhook
```

Set the Bot 1 webhook after deployment:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/set_customer_bot_webhook.py set --base-url https://api.tsplatform.ru
```

Verify Bot 1 webhook state without printing the bot token or webhook secret:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/set_customer_bot_webhook.py info
```

The Bot 1 webhook URL should be:

```text
https://api.tsplatform.ru/api/v1/telegram/customer-bot/webhook
```

Seller registration verification:

1. Open `https://seller.tsplatform.ru`.
2. Start seller registration and copy the `/start seller_<token>` command.
3. Open Bot 2 and send the command.
4. Confirm Bot 2 posts an approval request in `TELEGRAM_SELLER_CHAT_ID`.
5. Click Confirm in the seller group within 2 minutes.
6. Confirm Bot 2 sends the private verification code to the seller.
7. Enter the code in Seller Panel and confirm that seller login works.
8. In the seller group, verify `/sellers` shows `Seller ID for commands`.
9. Verify `/block_seller 6902459394` returns guidance to use Seller ID and does
   not produce a webhook 503.
10. On a test seller only, verify `/block_seller <Seller ID>` prevents
   login/current-user access without deleting seller history.

Smoke checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/products
curl http://localhost:8000/api/v1/categories
curl http://localhost:8000/api/v1/tags
```

Public production smoke checks:

```bash
curl -i https://api.tsplatform.ru/health
curl -i https://tsplatform.ru
curl -i https://seller.tsplatform.ru
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
- Customer Notifications MVP Phase 1 stores Bot 1 private-chat subscription and
  consent state only. It does not include campaigns, mass sending, delivery
  queues, or customer broadcast UI.
