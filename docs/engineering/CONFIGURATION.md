# Configuration catalog

Статус: канонический. Реальные values запрещены. `Required` означает required для соответствующей
production capability; Pydantic defaults делают часть полей technically optional.

Источник для backend rows: `backend/app/core/config.py`; backup rows:
`backend/scripts/backup_production.py`; build rows: Compose/Dockerfiles/frontend code.

## Core, data, auth, URLs

| Variable | Required | Format / safe default behavior | Sensitive | Impact / validation |
| --- | --- | --- | --- | --- |
| `APP_NAME` | No | text / API title | No | OpenAPI metadata |
| `APP_ENV` | Yes prod | `local|production|prod|staging` | No | activates production safety |
| `DEBUG` | Yes prod | bool / local true | No | error exposure; prod false |
| `API_V1_PREFIX` | No | URL path / `/api/v1` | No | all API routes |
| `POSTGRES_DB` | Compose | identifier / `telegram_shop` | No | database name |
| `POSTGRES_USER` | Compose | identifier | Sensitive-adjacent | DB login |
| `POSTGRES_PASSWORD` | Yes prod | secret string | Yes | DB/container; never document value |
| `DATABASE_URL` | Yes | asyncpg DSN | Yes | backend DB; driver must be async-compatible |
| `REDIS_URL` | Yes prod | Redis URL | Potentially | cache/rate limits |
| `JWT_SECRET_KEY` | Yes prod | long random secret | Yes | default rejected in prod/staging |
| `JWT_ALGORITHM` | No | `HS256` only | No | other values rejected by token code |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | positive integer / 60 | No | session lifetime |
| `CORS_ORIGINS` | Yes prod | comma-separated origins | No | `*` rejected prod/staging |
| `PUBLIC_UPLOADS_URL` | Yes | URL/path / `/uploads` | No | generated media URLs/mount path |
| `PUBLIC_API_BASE_URL` | Yes prod | absolute URL | No | webhook/public references |
| `PUBLIC_MINI_APP_BASE_URL` | Yes prod | absolute URL | No | links |
| `PUBLIC_SELLER_PANEL_BASE_URL` | Yes prod | absolute URL | No | links |
| `UPLOADS_DIR` | Yes | filesystem path / `uploads` | No | local binary storage |

## Telegram Bot 1, Bot 2, groups and channel

| Variable | Required | Format/default | Sensitive | Impact |
| --- | --- | --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot 2 | Telegram token | Yes | seller/admin bot and backup notification token |
| `TELEGRAM_WEBAPP_BOT_TOKEN` | Mini auth | Telegram token; falls back Bot 2 token | Yes | initData signature key; fallback should be avoided |
| `TELEGRAM_CUSTOMER_BOT_TOKEN` | Bot 1 | Telegram token | Yes | customer sends/campaigns/channel entry |
| `TELEGRAM_SELLER_BOT_USERNAME` | Seller auth | username without `@` | No | start link |
| `TELEGRAM_CUSTOMER_BOT_USERNAME` | Bot 1 | username without `@` | No | customer start links |
| `TELEGRAM_SELLER_WEBHOOK_SECRET` | Prod bot | random secret | Yes | seller webhook header/path |
| `TELEGRAM_CUSTOMER_WEBHOOK_SECRET` | Prod bot | random secret | Yes | customer webhook header |
| `TELEGRAM_ORDERS_CHAT_ID` | Ops | Telegram id | Yes | orders/payment/auth callbacks |
| `TELEGRAM_RETURNS_CHAT_ID` | Ops | Telegram id | Yes | return notifications/callbacks |
| `TELEGRAM_BACKUP_CHAT_ID` | Ops | Telegram id | Yes | backup status only |
| `TELEGRAM_SELLER_CHAT_ID` | Legacy | Telegram id | Yes | fallback for three dedicated chats |
| `TELEGRAM_MINI_APP_SHORT_NAME` | Optional | short name / empty | No | direct Mini App deep link form |
| `TELEGRAM_CHANNEL_ENTRY_START_PARAM` | No | Telegram start parameter / `channel_pin` | No | channel button |
| `TELEGRAM_AUTH_MAX_AGE_SECONDS` | No | integer / 86400 | No | initData freshness |
| `SELLER_REGISTRATION_EXPIRES_MINUTES` | No | integer / 30 | No | pending registration |
| `SELLER_VERIFICATION_CODE_EXPIRES_MINUTES` | No | integer / 10 | No | verification code |

## Logging, monitoring, cache and rate limits

| Variable | Required | Format/default | Sensitive | Impact |
| --- | --- | --- | --- | --- |
| `LOG_LEVEL` | No | level / `INFO` | No | log volume |
| `LOG_FORMAT` | No | `json` expected | No | operations ingestion |
| `ERROR_MONITORING_ENABLED` | No | bool / false | No | external monitoring |
| `SENTRY_DSN` | If enabled | DSN | Yes | external error transfer |
| `CACHE_ENABLED` | No | bool / true | No | public response caching |
| `CACHE_PUBLIC_PRODUCTS_TTL_SECONDS` | No | integer / 60 | No | product list TTL |
| `CACHE_PUBLIC_PRODUCT_DETAIL_TTL_SECONDS` | No | integer / 60 | No | detail TTL |
| `CACHE_TAXONOMY_TTL_SECONDS` | No | integer / 300 | No | category/tag TTL |
| `CACHE_BANNERS_TTL_SECONDS` | No | integer / 60 | No | banner TTL |
| `CACHE_REVIEWS_TTL_SECONDS` | No | integer / 120 | No | review TTL |
| `RATE_LIMIT_ENABLED` | No | bool / true | No | global middleware |
| `RATE_LIMIT_REDIS_ENABLED` | No | bool / true | No | distributed counter |
| `RATE_LIMIT_IN_MEMORY_FALLBACK_ENABLED` | No | bool / true | No | per-process fallback |
| `RATE_LIMIT_GLOBAL_REQUESTS` | No | integer / 600 | No | all API/IP |
| `RATE_LIMIT_GLOBAL_WINDOW_SECONDS` | No | integer / 60 | No | global window |
| `RATE_LIMIT_AUTH_REQUESTS` | No | integer / 10 | No | auth/IP |
| `RATE_LIMIT_AUTH_WINDOW_SECONDS` | No | integer / 60 | No | auth window |
| `RATE_LIMIT_UPLOAD_REQUESTS` | No | integer / 30 | No | upload/IP |
| `RATE_LIMIT_UPLOAD_WINDOW_SECONDS` | No | integer / 60 | No | upload window |
| `RATE_LIMIT_CHECKOUT_REQUESTS` | No | integer / 10 | No | checkout/IP |
| `RATE_LIMIT_CHECKOUT_WINDOW_SECONDS` | No | integer / 60 | No | checkout window |
| `RATE_LIMIT_PROMO_REQUESTS` | No | integer / 30 | No | validation/IP |
| `RATE_LIMIT_PROMO_WINDOW_SECONDS` | No | integer / 60 | No | promo window |
| `RATE_LIMIT_REVIEW_REQUESTS` | No | integer / 10 | No | review/IP |
| `RATE_LIMIT_REVIEW_WINDOW_SECONDS` | No | integer / 60 | No | review window |
| `RATE_LIMIT_TELEMETRY_REQUESTS` | No | integer / 60 | No | telemetry/IP |
| `RATE_LIMIT_TELEMETRY_WINDOW_SECONDS` | No | integer / 60 | No | telemetry window |
| `RATE_LIMIT_CUSTOMER_CAMPAIGN_REQUESTS` | No | integer / 30 | No | seller campaign mutations |
| `RATE_LIMIT_CUSTOMER_CAMPAIGN_WINDOW_SECONDS` | No | integer / 60 | No | campaign window |

## Telemetry and workers

| Variable | Required | Format/default | Sensitive | Impact |
| --- | --- | --- | --- | --- |
| `TELEMETRY_ENABLED` | No | bool / true | No | backend ingestion |
| `TELEMETRY_MAX_EVENTS_PER_BATCH` | No | integer / 25 | No | payload validation |
| `TELEMETRY_MAX_BODY_BYTES` | No | integer / 65536 | No | request limit |
| `TELEMETRY_SUCCESS_SAMPLE_RATE` | No | decimal / 0.2 | No | volume |
| `TELEMETRY_WEB_VITAL_SAMPLE_RATE` | No | decimal / 0.5 | No | frontend sample |
| `TELEMETRY_ROUTE_SAMPLE_RATE` | No | decimal / 0.25 | No | route sample |
| `TELEMETRY_NETWORK_SAMPLE_RATE` | No | decimal / 0.25 | No | network sample |
| `TELEMETRY_RETENTION_DAYS` | No | integer / 60 | No | cleanup policy in code |
| `TELEMETRY_CLEANUP_BATCH_SIZE` | No | integer / 500 | No | maintenance batch |
| `CUSTOMER_CAMPAIGN_BATCH_SIZE` | No | integer / 20 | No | worker batch |
| `CUSTOMER_CAMPAIGN_MAX_ATTEMPTS` | No | integer / 3 | No | terminal failures |
| `CUSTOMER_CAMPAIGN_RETRY_BASE_SECONDS` | No | integer / 60 | No | exponential retry |
| `CUSTOMER_CAMPAIGN_WORKER_ENABLED` | No | bool / true | No | lifespan worker; also needs Bot 1 token |
| `CUSTOMER_CAMPAIGN_WORKER_POLL_SECONDS` | No | integer / 5 | No | poll interval |
| `CUSTOMER_CAMPAIGN_SENDING_TIMEOUT_SECONDS` | No | integer / 300 | No | stale sending recovery |
| `MANUAL_PAYMENT_EXPIRATION_WORKER_ENABLED` | No | bool / true | No | payment expiry |
| `MANUAL_PAYMENT_EXPIRATION_POLL_SECONDS` | No | integer / 60 | No | poll interval |
| `OUTBOX_ENABLED` | No | bool / true | No | durable delivery worker |
| `OUTBOX_POLL_INTERVAL_SECONDS` | No | >0 decimal / 2 | No | validated positive |
| `OUTBOX_BATCH_SIZE` | No | >0 integer / 20 | No | validated positive |
| `OUTBOX_MAX_ATTEMPTS` | No | >0 integer / 8 | No | validated positive |
| `OUTBOX_LOCK_TIMEOUT_SECONDS` | No | >0 integer / 300 | No | stale claim recovery |
| `OUTBOX_RETRY_BASE_SECONDS` | No | >0 integer / 5 | No | backoff base |
| `OUTBOX_RETRY_MAX_SECONDS` | No | integer / 900 | No | must be ≥ base |
| `OUTBOX_WORKER_ID` | No | text / generated | No | diagnostic owner |

## Backup/Yandex

| Variable | Required | Format/default | Sensitive | Validation/impact |
| --- | --- | --- | --- | --- |
| `BACKUP_ENABLED` | Prod policy | bool / true | No | disables entire run if false |
| `BACKUP_ENVIRONMENT` | Yes | text / APP_ENV | No | archive identity |
| `BACKUP_LOCAL_DIR` | Yes | path / `backups` | No | archives/state/lock |
| `BACKUP_REMOTE_DIR` | Remote | Yandex path | No | offsite target |
| `BACKUP_INTERVAL_HOURS` | Yes policy | exactly 24 | No | script validation |
| `BACKUP_LOCAL_RETENTION_DAYS` | Yes policy | exactly 3 | No | script validation |
| `BACKUP_LOCAL_RETENTION_MAX_COUNT` | Yes policy | exactly 20 | No | script validation |
| `BACKUP_REMOTE_RETENTION_DAYS` | Yes policy | exactly 14 | No | script validation |
| `BACKUP_REMOTE_RETENTION_MAX_COUNT` | Yes policy | exactly 2 | No | script validation |
| `BACKUP_REMOTE_UPLOAD_CADENCE` | Yes policy | exactly 7 | No | successful local backups per upload |
| `BACKUP_RESTORE_VERIFY_ENABLED` | Yes policy | bool / true | No | restore check |
| `BACKUP_TELEGRAM_NOTIFICATIONS_ENABLED` | No | bool / true | No | run report |
| `YANDEX_CLIENT_ID` | Remote | OAuth credential | Yes | remote upload |
| `YANDEX_CLIENT_SECRET` | Remote | OAuth credential | Yes | remote upload |
| `YANDEX_REFRESH_TOKEN` | Remote | OAuth credential | Yes | remote upload |
| `BACKUP_RETENTION_DAYS` | Legacy | integer | No | compatibility fallback only |
| `BACKUP_RETENTION_MAX_COUNT` | Legacy | integer | No | compatibility fallback only |

## Frontend/Compose build-time

| Variable | Component | Default / impact | Sensitive |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | both standalone frontends | local API in examples | No |
| `MINI_APP_VITE_API_BASE_URL` | Compose build | `/api/v1` prod | No |
| `SELLER_PANEL_VITE_API_BASE_URL` | Compose build | `/api/v1` prod | No |
| `VITE_TELEGRAM_BOT_USERNAME` | Mini App | customer bot username | No |
| `VITE_TELEMETRY_DISABLED` | Mini App | false in example | No |

## Drift

`backend/.env.example` and `.env.production.example` omit all six
`CUSTOMER_CAMPAIGN_*` variables and two `RATE_LIMIT_CUSTOMER_CAMPAIGN_*` variables. They also do not
list `VITE_TELEMETRY_DISABLED`; Mini App example does. Samples contain instructional placeholder text
inside sensitive fields and must not be deployed without replacement. Real `.env` files were not read
or modified during this audit.

