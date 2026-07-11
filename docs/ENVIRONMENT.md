# Environment Reference

This document lists environment conventions and public variable names. It intentionally uses placeholders only. Do not copy real production secrets into documentation, pull requests, issue comments, screenshots, or chat messages.

## File Conventions

| File | Purpose |
| --- | --- |
| `backend/.env` | Local backend development and local checks |
| `backend/.env.production` | Production/VDS work and production-domain checks on the server |
| `mini-app/.env.local` | Optional local Mini App overrides |
| `seller-panel/.env.local` | Optional local Seller Panel overrides |

Production uses:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ...
```

The production env file is not documentation. It must contain real values only on the server or in a secure secret store.

## Safe Placeholders

Use these placeholders in docs and examples:

| Placeholder | Meaning |
| --- | --- |
| `<SECRET>` | Generic secret value |
| `<BOT_TOKEN>` | Telegram bot token |
| `<DATABASE_URL>` | SQLAlchemy database URL |
| `<JWT_SECRET>` | JWT signing secret |
| `-100xxxxxxxxxx` | Placeholder Telegram supergroup/channel chat id |

## Backend Core Settings

| Variable | Purpose | Example placeholder |
| --- | --- | --- |
| `APP_NAME` | FastAPI app display name | `Telegram Shop Platform API` |
| `APP_ENV` | Runtime environment such as `local` or `production` | `production` |
| `DEBUG` | Enables development debug behavior | `false` |
| `API_V1_PREFIX` | API prefix | `/api/v1` |
| `DATABASE_URL` | Async SQLAlchemy PostgreSQL URL | `<DATABASE_URL>` |
| `REDIS_URL` | Redis URL for cache, rate limiting, and temporary state | `redis://redis:6379/0` |
| `JWT_SECRET_KEY` | JWT signing secret | `<JWT_SECRET>` |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `60` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins | `https://stylexac.ru,https://mini.stylexac.ru,https://seller.stylexac.ru` |
| `LOG_LEVEL` | Backend log level | `INFO` |
| `LOG_FORMAT` | Backend log format | `json` |

Production safety validation rejects the default JWT secret and wildcard CORS origins in production-like environments.

## Public URL Settings

| Variable | Purpose | Production value pattern |
| --- | --- | --- |
| `PUBLIC_API_BASE_URL` | Public API origin | `https://api.stylexac.ru` |
| `PUBLIC_MINI_APP_BASE_URL` | Public Mini App origin | `https://mini.stylexac.ru` |
| `PUBLIC_SELLER_PANEL_BASE_URL` | Public Seller Panel origin | `https://seller.stylexac.ru` |
| `PUBLIC_UPLOADS_URL` | Public uploads base path or URL | `/uploads` |
| `UPLOADS_DIR` | Backend filesystem upload directory | `uploads` |

## Telegram Settings

| Variable | Owner | Purpose | Placeholder |
| --- | --- | --- | --- |
| `TELEGRAM_WEBAPP_BOT_TOKEN` | Mini App auth | Validates customer Mini App `initData` | `<BOT_TOKEN>` |
| `TELEGRAM_CUSTOMER_BOT_TOKEN` | Bot 1 | Customer bot token for `/start`, `/stop`, service notifications, campaigns, channel entry | `<BOT_TOKEN>` |
| `TELEGRAM_CUSTOMER_BOT_USERNAME` | Bot 1 | Customer bot username used for Mini App links | `CheckYouStyleBot` |
| `TELEGRAM_CUSTOMER_WEBHOOK_SECRET` | Bot 1 | Secret header for customer bot webhook | `<SECRET>` |
| `TELEGRAM_BOT_TOKEN` | Bot 2 | Seller/admin/auth-related bot token | `<BOT_TOKEN>` |
| `TELEGRAM_SELLER_BOT_USERNAME` | Bot 2 | Seller/admin bot username | `<SECRET>` |
| `TELEGRAM_ORDERS_CHAT_ID` | Bot 2 | Orders group for order notifications, seller/admin commands, manual payment callbacks, seller registration approval callbacks | `-100xxxxxxxxxx` |
| `TELEGRAM_RETURNS_CHAT_ID` | Bot 2 | Returns group for return request notifications, return media, approve/reject callbacks | `-100xxxxxxxxxx` |
| `TELEGRAM_BACKUP_CHAT_ID` | Bot 2 backup script | Backup success/failure notification group | `-100xxxxxxxxxx` |
| `TELEGRAM_SELLER_CHAT_ID` | Bot 2 | Legacy seller/admin notification chat id used only as a migration fallback | `-100xxxxxxxxxx` |
| `TELEGRAM_SELLER_WEBHOOK_SECRET` | Bot 2 | Secret header for seller bot webhook | `<SECRET>` |
| `TELEGRAM_MINI_APP_SHORT_NAME` | Bot 1 link builder | Optional short-name Mini App path for direct links | `<SECRET>` |
| `TELEGRAM_CHANNEL_ENTRY_START_PARAM` | Bot 1 link builder | Channel entry start parameter | `channel_pin` |
| `TELEGRAM_AUTH_MAX_AGE_SECONDS` | Auth | Maximum age for Telegram `auth_date` | `86400` |

Bot 1 handles buyer-facing and channel-entry flows. Bot 2 handles seller/admin/auth-related flows. Do not swap these tokens.

Bot 2 operational routing is split by chat purpose: orders/seller/admin commands and callbacks use `TELEGRAM_ORDERS_CHAT_ID`, return request notifications and callbacks use `TELEGRAM_RETURNS_CHAT_ID`, and backup notifications use `TELEGRAM_BACKUP_CHAT_ID`. `TELEGRAM_SELLER_CHAT_ID` remains only as a legacy fallback while production env files are migrated. Telegram group topic/thread ids are not supported yet.

Fallback behavior:

- Orders: `TELEGRAM_ORDERS_CHAT_ID` -> `TELEGRAM_SELLER_CHAT_ID`.
- Returns: `TELEGRAM_RETURNS_CHAT_ID` -> `TELEGRAM_SELLER_CHAT_ID`.
- Backup: `TELEGRAM_BACKUP_CHAT_ID` -> `TELEGRAM_SELLER_CHAT_ID`.
- `TELEGRAM_SELLER_CHAT_ID` is legacy fallback only; do not use it as the desired split-chat configuration.

Safe Telegram diagnostics:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend \
  python scripts/telegram_diagnostics.py --env-file .env.production
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend \
  python scripts/telegram_diagnostics.py --env-file .env.production --send
```

The diagnostic helper checks Bot 2 `getMe` and `getChat` for the configured orders, returns, backup, and legacy seller chats. It does not print bot tokens and sends messages only with `--send`.

## Cache, Rate Limit, and Telemetry Settings

| Variable | Purpose |
| --- | --- |
| `CACHE_ENABLED` | Enables Redis-backed cache where implemented |
| `CACHE_PUBLIC_PRODUCTS_TTL_SECONDS` | Public product list cache TTL |
| `CACHE_PUBLIC_PRODUCT_DETAIL_TTL_SECONDS` | Public product detail cache TTL |
| `CACHE_TAXONOMY_TTL_SECONDS` | Category/tag cache TTL |
| `CACHE_BANNERS_TTL_SECONDS` | Public banner cache TTL |
| `CACHE_REVIEWS_TTL_SECONDS` | Public review cache TTL |
| `RATE_LIMIT_ENABLED` | Enables API rate limiting |
| `RATE_LIMIT_REDIS_ENABLED` | Uses Redis for rate limiting when available |
| `RATE_LIMIT_IN_MEMORY_FALLBACK_ENABLED` | Allows local fallback if Redis rate limiting is unavailable |
| `RATE_LIMIT_GLOBAL_REQUESTS` | Global request limit |
| `RATE_LIMIT_GLOBAL_WINDOW_SECONDS` | Global rate-limit window |
| `RATE_LIMIT_AUTH_REQUESTS` | Auth request limit |
| `RATE_LIMIT_UPLOAD_REQUESTS` | Upload request limit |
| `RATE_LIMIT_CHECKOUT_REQUESTS` | Checkout request limit |
| `RATE_LIMIT_PROMO_REQUESTS` | Promo validation request limit |
| `RATE_LIMIT_REVIEW_REQUESTS` | Review request limit |
| `RATE_LIMIT_TELEMETRY_REQUESTS` | Telemetry ingestion request limit |
| `RATE_LIMIT_CUSTOMER_CAMPAIGN_REQUESTS` | Customer campaign admin request limit |
| `TELEMETRY_ENABLED` | Enables telemetry ingestion |
| `TELEMETRY_RETENTION_DAYS` | Analytics event retention period |

## Background Worker Settings

| Variable | Purpose |
| --- | --- |
| `CUSTOMER_CAMPAIGN_BATCH_SIZE` | Campaign delivery rows processed per batch |
| `CUSTOMER_CAMPAIGN_MAX_ATTEMPTS` | Maximum campaign delivery attempts |
| `CUSTOMER_CAMPAIGN_RETRY_BASE_SECONDS` | Base retry delay |
| `CUSTOMER_CAMPAIGN_WORKER_ENABLED` | Enables campaign worker in backend lifespan |
| `CUSTOMER_CAMPAIGN_WORKER_POLL_SECONDS` | Campaign worker polling interval |
| `CUSTOMER_CAMPAIGN_SENDING_TIMEOUT_SECONDS` | Campaign sending timeout |
| `MANUAL_PAYMENT_EXPIRATION_WORKER_ENABLED` | Enables manual payment expiration worker |
| `MANUAL_PAYMENT_EXPIRATION_POLL_SECONDS` | Manual payment expiration polling interval |

## Backup Settings

| Variable | Purpose | Production placeholder |
| --- | --- | --- |
| `BACKUP_ENABLED` | Enables production backup script | `true` |
| `BACKUP_ENVIRONMENT` | Backup environment label | `production` |
| `BACKUP_LOCAL_DIR` | Local backup staging directory | `backups` |
| `BACKUP_REMOTE_DIR` | Yandex Disk remote directory | `/TelegramShopPlatform/storage` |
| `BACKUP_INTERVAL_HOURS` | Expected backup interval for validation | `24` |
| `BACKUP_LOCAL_RETENTION_DAYS` | Local archive retention by age | `3` |
| `BACKUP_LOCAL_RETENTION_MAX_COUNT` | Local archive retention by count guard | `20` |
| `BACKUP_REMOTE_RETENTION_DAYS` | Yandex Disk archive retention by age | `14` |
| `BACKUP_REMOTE_RETENTION_MAX_COUNT` | Yandex Disk archive retention by count guard | `2` |
| `BACKUP_REMOTE_UPLOAD_CADENCE` | Upload every Nth successful local backup | `7` |
| `BACKUP_RESTORE_VERIFY_ENABLED` | Enables restore verification in backup flow | `true` |
| `BACKUP_TELEGRAM_NOTIFICATIONS_ENABLED` | Enables Telegram backup notifications | `true` |
| `YANDEX_CLIENT_ID` | Yandex Disk OAuth client id | `<SECRET>` |
| `YANDEX_CLIENT_SECRET` | Yandex Disk OAuth client secret | `<SECRET>` |
| `YANDEX_REFRESH_TOKEN` | Yandex Disk OAuth refresh token | `<SECRET>` |

Backup notifications use `TELEGRAM_BACKUP_CHAT_ID` and fall back to `TELEGRAM_SELLER_CHAT_ID` only for legacy env compatibility. Yandex Disk uploads can timeout and retry; operators must confirm the daily local backup status and the remote upload status in systemd journal logs.

## Frontend Build Variables

| Variable | App | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Mini App and Seller Panel | Runtime API base URL or `/api/v1` when reverse-proxied |
| `VITE_TELEGRAM_BOT_USERNAME` | Mini App | Bot username used by Mini App helper links |
| `VITE_TELEMETRY_DISABLED` | Mini App | Disables Mini App telemetry when set to `true` |
| `VITE_APP_VERSION` | Mini App | Optional build/version marker |
| `MINI_APP_VITE_API_BASE_URL` | Production compose build arg | Supplies Mini App `VITE_API_BASE_URL` |
| `SELLER_PANEL_VITE_API_BASE_URL` | Production compose build arg | Supplies Seller Panel `VITE_API_BASE_URL` |

Do not hardcode production API URLs in frontend source. Use environment variables and the production reverse proxy.

## Secret Handling Rules

- Do not commit `.env`, `.env.production`, uploaded user files, DB dumps, private keys, bot tokens, JWT secrets, or external storage tokens.
- Do not include raw Telegram tokens or raw production env content in docs.
- Do not log raw Telegram `initData`.
- Use sanitized diagnostics for auth and Telegram delivery failures.

## Transactional Outbox Settings

| Variable | Default | Purpose |
| --- | ---: | --- |
| `OUTBOX_ENABLED` | `true` | Starts the lifespan processor; producers still enqueue durably when disabled. |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `2` | Idle delay between polls. |
| `OUTBOX_BATCH_SIZE` | `20` | Maximum events claimed per transaction. |
| `OUTBOX_MAX_ATTEMPTS` | `8` | Per-consumer attempts before terminal failure. |
| `OUTBOX_LOCK_TIMEOUT_SECONDS` | `300` | Age after which an abandoned processing claim is recoverable; an owned claim renews every one third of this interval. |
| `OUTBOX_RETRY_BASE_SECONDS` | `5` | Initial exponential retry delay. |
| `OUTBOX_RETRY_MAX_SECONDS` | `900` | Retry delay cap. |
| `OUTBOX_WORKER_ID` | generated | Optional stable diagnostic worker name; never put secrets in it. |

All positive numeric outbox settings are validated at startup, and the retry maximum must be at
least the retry base. The derived heartbeat interval is `OUTBOX_LOCK_TIMEOUT_SECONDS / 3`, which
is always below half the stale timeout. Worker IDs are diagnostic labels; per-claim UUID tokens
provide ownership fencing.
