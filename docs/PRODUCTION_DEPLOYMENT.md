# Production Deployment

Sprint 14 adds a small Docker Compose production profile for MVP staging or single-node production.

Production domain map:

- `https://stylexac.ru` and `https://www.stylexac.ru`: Mini App
- `https://mini.stylexac.ru`: Mini App
- `https://api.stylexac.ru`: backend API
- `https://seller.stylexac.ru`: Seller Panel

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
- `PUBLIC_API_BASE_URL=https://api.stylexac.ru`
- `PUBLIC_UPLOADS_URL=https://api.stylexac.ru/uploads`
- `PUBLIC_MINI_APP_BASE_URL=https://mini.stylexac.ru`
- `PUBLIC_SELLER_PANEL_BASE_URL=https://seller.stylexac.ru`
- `TELEGRAM_WEBAPP_BOT_TOKEN`
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_SELLER_CHAT_ID` for Bot 2 seller verification,
  seller notifications, and seller-chat broadcast
- `TELEGRAM_SELLER_BOT_USERNAME` if the Seller Panel should show a direct `t.me`
  start link during registration
- `TELEGRAM_SELLER_WEBHOOK_SECRET` for the protected Bot 2 webhook
  `X-Telegram-Bot-Api-Secret-Token` header
- `TELEGRAM_CUSTOMER_BOT_TOKEN` for Bot 1 customer notification registry
  webhook setup, service notification delivery, and customer campaigns
- `TELEGRAM_CUSTOMER_BOT_USERNAME` for Mini App customer notification start
  links
- `TELEGRAM_CUSTOMER_WEBHOOK_SECRET` for the protected Bot 1 webhook
  `X-Telegram-Bot-Api-Secret-Token` header
- `MANUAL_PAYMENT_EXPIRATION_WORKER_ENABLED=true`
- `MANUAL_PAYMENT_EXPIRATION_POLL_SECONDS=60` (or another positive polling interval)
- cache, rate limit, and customer campaign batch settings from
  `backend/.env.production.example`

Frontend:

- `VITE_API_BASE_URL` for both `mini-app` and `seller-panel`
- `VITE_TELEGRAM_BOT_USERNAME` for Mini App UI links only, not bot tokens

## Start

Before deploying this migration, create and verify a PostgreSQL plus uploads
backup. The release requires rebuilding the backend, Mini App, and Seller Panel,
then applying Alembic head `20260614_0027`. The persistent uploads volume must
allow the backend to create and write `/app/uploads/payment_receipts/`.

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

Manual SBP payments require migration head `20260614_0027`. Seller Portal
email/password auth, seller approval, and Customer Notifications Phase 2 remain
included in that migration chain. Bot 2 is connected through:

```text
POST /api/v1/telegram/seller-bot/webhook
```

Set the webhook after deployment:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/set_seller_bot_webhook.py set --base-url https://api.stylexac.ru
```

Verify Telegram webhook state without printing the bot token:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/set_seller_bot_webhook.py info
```

The webhook URL should be:

```text
https://api.stylexac.ru/api/v1/telegram/seller-bot/webhook
```

Bot 1 customer notification registry is connected through:

```text
POST /api/v1/telegram/customer-bot/webhook
```

Set the Bot 1 webhook after deployment:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/set_customer_bot_webhook.py set --base-url https://api.stylexac.ru
```

Verify Bot 1 webhook state without printing the bot token or webhook secret:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/set_customer_bot_webhook.py info
```

The Bot 1 webhook URL should be:

```text
https://api.stylexac.ru/api/v1/telegram/customer-bot/webhook
```

Customer campaign staging flow before production enablement:

1. Use one internal Telegram account and open Bot 1 with `/start`.
2. In `https://seller.stylexac.ru`, verify Customer Notifications shows the
   internal recipient with a masked chat id and the expected opt-in state.
3. Create a plain-text template or draft campaign.
4. Run preview and confirm marketing counts exclude non-opted-in recipients.
5. Send a test message; this uses the current seller/admin Bot 1 subscription,
   not Bot 2 seller chat metadata.
6. Start a tiny internal campaign and process one bounded batch.
7. Confirm delivery report counts and sanitized errors before enabling larger
   production campaigns.

Seller registration verification:

1. Open `https://seller.stylexac.ru`.
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

Manual SBP payment verification:

1. In Seller Panel settings, save the SBP phone and enable manual payment.
2. Create a Mini App order and confirm the 30-minute payment page shows the
   snapshotted phone, amount, bank/recipient when configured, and order comment.
3. Upload a receipt and click `Я оплатил`.
4. Confirm Bot 2 posts only to `TELEGRAM_SELLER_CHAT_ID`, then approve or reject
   with an active seller/admin account.
5. Confirm the original Bot 2 review message loses its inline buttons and shows
   the final approval/rejection result. If Telegram cannot edit it, confirm a
   final-state follow-up appears.
6. Confirm approval moves the order to processing without returning stock.
7. Confirm rejection or expiry cancels the order and returns stock exactly once.
8. Change seller payment settings and confirm the existing payment snapshot is
   unchanged while a new checkout uses the new values.

Order customer messaging:

1. Apply Alembic revision `20260615_0029`.
2. Open an order in Seller Panel and use `Отправить сообщение`.
3. Verify text-only and photo-only sends arrive in the customer's Bot 1 chat.
4. Verify a customer without an active Bot 1 private chat returns a clear seller
   error and no Bot 2 customer message is attempted.

Bot 2 token and seller group configuration are required for Telegram review
buttons. Seller Panel review remains available without Telegram delivery. Bot 1
token is required only when customer payment notifications are enabled, and Bot
2 must never send customer messages.

Smoke checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/products
curl http://localhost:8000/api/v1/categories
curl http://localhost:8000/api/v1/tags
```

Public production smoke checks:

```bash
curl -i https://api.stylexac.ru/health
curl -i https://stylexac.ru
curl -i https://www.stylexac.ru
curl -i https://mini.stylexac.ru
curl -i https://seller.stylexac.ru
```

## Services

- Backend API: `http://localhost:8000`
- Seller Panel: `http://localhost:8080`
- Mini App static bundle: `http://localhost:8081`
- PostgreSQL: private compose network, persistent `postgres_prod_data` volume
- Redis: private compose network, persistent `redis_prod_data` volume
- Uploads: persistent `uploads_data` volume mounted at `/app/uploads`
- Manual payment receipts: writable `/app/uploads/payment_receipts/` inside that volume

## Migrations

- Add new Alembic migrations for schema changes.
- Do not edit old migrations after they have been shared.
- Review generated migrations before running them in staging or production.
- Run `alembic upgrade head` during deployment before routing traffic to a new backend build.
- Keep downgrade functions when the existing migration style supports them.

## Observability

Application logs are JSON by default and include request id, method, path, status, and duration.
Error monitoring is prepared through `ERROR_MONITORING_ENABLED` and `SENTRY_DSN`, but no external SDK is required for MVP.

## Production Backups

Production backups run from the VDS host and target the production Compose
services. PostgreSQL is dumped in custom format, uploads are archived
separately, Redis is not backed up as durable data, and `.env.production` is
not included in normal backup archives.

Required backup variables in `backend/.env.production`:

```text
BACKUP_ENABLED=true
BACKUP_ENVIRONMENT=production
BACKUP_LOCAL_DIR=backups
BACKUP_REMOTE_DIR=/TelegramShopPlatform/storage
BACKUP_INTERVAL_HOURS=6
BACKUP_RETENTION_DAYS=5
BACKUP_RETENTION_MAX_COUNT=20
BACKUP_RESTORE_VERIFY_ENABLED=true
YANDEX_CLIENT_ID=<placeholder>
YANDEX_CLIENT_SECRET=<placeholder>
YANDEX_REFRESH_TOKEN=<placeholder>
BACKUP_TELEGRAM_NOTIFICATIONS_ENABLED=true
```

The script also uses existing Bot 2 variables:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_SELLER_CHAT_ID
```

Validate on the VDS:

```bash
python backend/scripts/backup_production.py validate-config --strict-yandex
```

Run a manual production backup:

```bash
python backend/scripts/backup_production.py run
```

Every successful run restore-verifies the PostgreSQL dump in a temporary
database, verifies the uploads archive is readable, uploads the final archive to
Yandex Disk under `/TelegramShopPlatform/storage/`, checks remote file size,
applies 5-day / 20-archive local and remote retention, and sends a sanitized
Bot 2 notification.

Systemd templates are provided but not enabled automatically:

```text
scripts/systemd/telegram-shop-backup.service
scripts/systemd/telegram-shop-backup.timer
```

Install manually, adjusting `/opt/TelegramShopPlatform` if the VDS uses another
path:

```bash
sudo cp /opt/TelegramShopPlatform/scripts/systemd/telegram-shop-backup.service /etc/systemd/system/
sudo cp /opt/TelegramShopPlatform/scripts/systemd/telegram-shop-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-shop-backup.timer
systemctl list-timers telegram-shop-backup.timer
```

See `docs/BACKUP_AND_RESTORE.md` and `docs/BACKUP_STRATEGY.md` for restore
drill steps, failure behavior, and notification contents.

## Known MVP Limits

- Compose is intended for MVP staging or a single-node deployment, not high availability.
- Public review and seller moderation lists keep their current response shape; review admin pagination is documented as a later compatibility-safe improvement.
- Redis is a cache and rate-limit accelerator. Public endpoints fall back to PostgreSQL if Redis is unavailable.
- Customer Notifications Phase 2 supports controlled Bot 1 campaigns through
  templates, materialized delivery rows, and bounded process-batch processing.
  Recipient exports, arbitrary database interpolation, non-plain parse modes,
  and a separate worker process remain out of scope.
