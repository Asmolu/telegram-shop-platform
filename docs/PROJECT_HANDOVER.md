# Project Handover

This handover describes the current production state of TelegramShopPlatform / ICON STORE after the latest production release. It is written for a new developer or operator who needs to understand the deployed system, business flows, release operations, and known limits without reading old sprint chat or stale domain notes.

## 1. Project Overview

Project name: TelegramShopPlatform / ICON STORE.

Current deployed domain family: `stylexac.ru`.

Purpose: a Telegram Mini App marketplace/shop platform with a customer storefront, seller/admin operations, Telegram bot integrations, and production backup operations.

Main roles:

- `USER`: customer using the Mini App.
- `SELLER`: seller/operator using the Seller Panel and seller bot flows.
- `ADMIN`: elevated operator with seller/admin access.

Main interfaces:

- Mini App: customer storefront at `https://stylexac.ru` and `https://mini.stylexac.ru`.
- Seller Panel: seller/admin dashboard at `https://seller.stylexac.ru`.
- Backend API: FastAPI service at `https://api.stylexac.ru`.
- Customer Telegram bot: Bot 1 for customer-facing flows.
- Seller/notification Telegram bot: Bot 2 for seller/admin/auth, order, return, and backup operations.

Main business flows:

- Browse mixed feed, categories, search, tags, suggestions, product detail, and related products.
- Browse Looks/outfits, open Look details, select components, choose independent clothing and footwear sizes, and add selected components to cart.
- Manage cart selection, promo codes, checkout, manual payment, order success, order detail, and order history.
- Create and manage returns after delivered orders, including media attachments, seller approval/rejection, refund recording, and explicit restock.
- Manage seller orders, manual payment callbacks, product catalog, variants, inventory, categories/tags, banners, promo codes, reviews, customer notifications, channel entry, returns, and Looks.
- Run production deploy, backup, diagnostics, smoke checks, and incident operations.

## 2. Architecture

Production stack:

- Backend: Python 3.12+, FastAPI, Uvicorn, SQLAlchemy 2.0 async ORM, Alembic, PostgreSQL 16, Redis 7, Pytest, Ruff.
- Mini App: React, Vite, TypeScript.
- Seller Panel: React, Vite, TypeScript.
- Telegram bots:
  - Bot 1: customer bot.
  - Bot 2: seller/notification bot.
- Storage:
  - PostgreSQL is the source of truth.
  - Redis is used for cache, rate limiting, and temporary state where implemented.
  - Local uploads store product, category, banner, Look, review, campaign, payment receipt, and return media files.
  - PostgreSQL stores file paths/URLs only, not binary file contents.
- Deployment:
  - Docker Compose production stack.
  - Host Caddy reverse proxy and TLS termination.
  - systemd backup service and timer.
  - Backups upload to Yandex Disk.

Backend modules live under `backend/app/modules/<feature>/`:

```text
backend/app/modules/<feature>/
├── router.py
├── schemas.py
├── service.py
└── repository.py
```

Layering rule:

- Routers parse requests, call services, and return responses.
- Services own business rules, transactions, authorization decisions, and side-effect ordering.
- Repositories own SQLAlchemy queries.
- Models currently live in `backend/app/db/models.py`.
- Alembic migrations are required for database schema changes.

Current module-level architecture:

- `products`: product catalog, images, variants, inventory, product search, public detail, slug/SKU generation, visibility, returnability, size groups, related products.
- `categories`: categories, images, public category resolution, route alias creation on slug changes.
- `tags`: tags, images, public taxonomy.
- `feed`: mixed public feed combining products and Looks.
- `looks`: independent Look/outfit entities, Look images, LookItems referencing products, Look cart add.
- `cart`: cart items, selection, totals, Look source grouping.
- `orders`: transactional checkout, immutable order item snapshots, stock decrement, order status changes, delivered timestamp, notification events.
- `manual_payments`: manual SBP-style payment settings, receipt upload, approval/rejection, expiration worker.
- `promo_codes`: coupons, validation, usage limits, `CouponUsage` snapshots.
- `banners`: banner CRUD, display types, public delivery, click/view analytics.
- `returns`: return request eligibility, creation, attachments, lifecycle, refund/restock processing.
- `route_aliases`: old slug storage and resolution for products, categories, and Looks.
- `notifications`: seller/admin notification helpers.
- `customer_notifications`: customer Bot 1 subscriptions, write access, service notifications, campaigns, delivery reports.
- `telegram`: Bot 1/Bot 2 webhook routing and Telegram transport behavior.
- `seller_auth`: seller/admin Telegram auth and registration approval.
- `seller_bot`: Bot 2 seller/admin bot flows.
- `uploads`: local upload validation, storage, URL building, derivative image support.
- `analytics`: privacy-safe behavior events and dashboard summaries.
- `audit`: critical seller/admin action audit logs.
- `auth`, `users`, `favorites`, `reviews`, `statistics`, `channel_entry`, `idempotency`: auth/session, role/user data, favorites, moderated reviews, dashboard stats, channel entry publication, and idempotent checkout support.

## 3. Production Domains and Services

Current production domains:

| Purpose | Domain |
| --- | --- |
| Main / Mini App entry | `https://stylexac.ru` |
| Mini App direct | `https://mini.stylexac.ru` |
| API | `https://api.stylexac.ru` |
| Seller Panel | `https://seller.stylexac.ru` |

Old `tsplatform.ru` domains are stale and must not be documented or treated as current production domains. The current domain family is `stylexac.ru`.

Current production path:

```bash
/opt/telegram-shop
```

Compose service mapping:

| Service | Purpose | Public routing |
| --- | --- | --- |
| `backend` | FastAPI API, uploads, bot webhooks, background workers | `https://api.stylexac.ru`, plus `/api/*` and `/uploads/*` reverse-proxied from frontend domains |
| `mini-app` | Built Mini App static site | `https://stylexac.ru`, `https://mini.stylexac.ru` |
| `seller-panel` | Built Seller Panel static site | `https://seller.stylexac.ru` |
| `postgres` | PostgreSQL 16 data store | Internal Docker network only |
| `redis` | Redis 7 cache/rate-limit/temporary store | Internal Docker network only |
| Caddy | Host TLS/reverse proxy | Public `stylexac.ru` routes |

Host Caddy routes `api.stylexac.ru` to the backend container, routes `stylexac.ru` and `mini.stylexac.ru` to the Mini App container, routes `seller.stylexac.ru` to the Seller Panel container, and proxies `/api/*` and `/uploads/*` to the backend from frontend domains.

## 4. Environment Variables

Real values live in `backend/.env.production` on the production host or a secure secret store. Documentation and examples must use placeholders only.

Core backend settings:

| Variable | Purpose | Safe example |
| --- | --- | --- |
| `APP_NAME` | FastAPI app display name | `Telegram Shop Platform API` |
| `APP_ENV` | Runtime environment | `production` |
| `DEBUG` | Debug behavior | `false` |
| `API_V1_PREFIX` | Versioned API prefix | `/api/v1` |
| `DATABASE_URL` | Async SQLAlchemy PostgreSQL URL | `postgresql+asyncpg://<USER>:<PASSWORD>@postgres:5432/<DB>` |
| `POSTGRES_DB` | PostgreSQL database name for compose and backups | `telegram_shop` |
| `POSTGRES_USER` | PostgreSQL user for compose and backups | `telegram_shop` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `<SECRET>` |
| `REDIS_URL` | Redis URL | `redis://redis:6379/0` |
| `JWT_SECRET_KEY` | JWT signing secret | `<JWT_SECRET>` |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `60` |
| `CORS_ORIGINS` | Allowed browser origins | `https://stylexac.ru,https://mini.stylexac.ru,https://seller.stylexac.ru` |
| `LOG_LEVEL` | Backend log level | `INFO` |
| `LOG_FORMAT` | Log format | `json` |

Public URL and upload settings:

| Variable | Purpose | Safe example |
| --- | --- | --- |
| `PUBLIC_API_BASE_URL` | Public API origin | `https://api.stylexac.ru` |
| `PUBLIC_MINI_APP_BASE_URL` | Public Mini App origin | `https://mini.stylexac.ru` |
| `PUBLIC_SELLER_PANEL_BASE_URL` | Public Seller Panel origin | `https://seller.stylexac.ru` |
| `PUBLIC_UPLOADS_URL` | Public uploads mount/base URL | `/uploads` |
| `UPLOADS_DIR` | Backend filesystem upload directory | `uploads` |

Telegram settings:

| Variable | Owner | Purpose | Safe example |
| --- | --- | --- | --- |
| `TELEGRAM_WEBAPP_BOT_TOKEN` | Mini App auth / Bot 1 | Validates customer Mini App `initData` | `<BOT_TOKEN>` |
| `TELEGRAM_CUSTOMER_BOT_TOKEN` | Bot 1 | Customer `/start`, `/stop`, service notifications, campaigns, channel entry | `<BOT_TOKEN>` |
| `TELEGRAM_CUSTOMER_BOT_USERNAME` | Bot 1 | Customer bot username for links | `<BOT_USERNAME>` |
| `TELEGRAM_CUSTOMER_WEBHOOK_SECRET` | Bot 1 | Customer webhook secret header | `<SECRET>` |
| `TELEGRAM_BOT_TOKEN` | Bot 2 | Seller/admin/auth, orders, returns, backups | `<BOT_TOKEN>` |
| `TELEGRAM_SELLER_BOT_USERNAME` | Bot 2 | Seller/admin bot username | `<BOT_USERNAME>` |
| `TELEGRAM_SELLER_WEBHOOK_SECRET` | Bot 2 | Seller webhook secret header | `<SECRET>` |
| `TELEGRAM_ORDERS_CHAT_ID` | Bot 2 | Orders group, seller/admin commands, manual payment callbacks, seller registration callbacks | `-100xxxxxxxxxx` |
| `TELEGRAM_RETURNS_CHAT_ID` | Bot 2 | Returns group and return request callbacks | `-100xxxxxxxxxx` |
| `TELEGRAM_BACKUP_CHAT_ID` | Bot 2 backup script | Backup success/failure notifications | `-100xxxxxxxxxx` |
| `TELEGRAM_SELLER_CHAT_ID` | Bot 2 | Legacy fallback chat id | `-100xxxxxxxxxx` |
| `TELEGRAM_MINI_APP_SHORT_NAME` | Bot 1 link builder | Optional Telegram Mini App short name | `<SHORT_NAME>` |
| `TELEGRAM_CHANNEL_ENTRY_START_PARAM` | Bot 1 link builder | Channel entry start parameter | `channel_pin` |
| `TELEGRAM_AUTH_MAX_AGE_SECONDS` | Auth | Maximum accepted `initData` age | `86400` |

Telegram fallback behavior:

- Orders notifications and seller/admin bot group operations use `TELEGRAM_ORDERS_CHAT_ID`, falling back to `TELEGRAM_SELLER_CHAT_ID` only when orders chat is unset.
- Return request notifications use `TELEGRAM_RETURNS_CHAT_ID`, falling back to `TELEGRAM_SELLER_CHAT_ID` only when returns chat is unset.
- Backup notifications use `TELEGRAM_BACKUP_CHAT_ID`, falling back to `TELEGRAM_SELLER_CHAT_ID` only when backup chat is unset.
- `TELEGRAM_SELLER_CHAT_ID` remains a legacy migration fallback. Prefer setting all split chat ids explicitly.

Backup settings:

| Variable | Purpose | Safe example |
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
| `BACKUP_RESTORE_VERIFY_ENABLED` | Enables restore verification inside backup flow | `true` |
| `BACKUP_TELEGRAM_NOTIFICATIONS_ENABLED` | Enables Telegram backup notifications | `true` |
| `YANDEX_CLIENT_ID` | Yandex Disk OAuth client id | `<SECRET>` |
| `YANDEX_CLIENT_SECRET` | Yandex Disk OAuth client secret | `<SECRET>` |
| `YANDEX_REFRESH_TOKEN` | Yandex Disk OAuth refresh token | `<SECRET>` |

Frontend build settings:

| Variable | App | Purpose | Safe example |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | Mini App / Seller Panel | API base used by frontend builds | `/api/v1` |
| `MINI_APP_VITE_API_BASE_URL` | Compose build arg | Mini App API base | `/api/v1` |
| `SELLER_PANEL_VITE_API_BASE_URL` | Compose build arg | Seller Panel API base | `/api/v1` |
| `VITE_TELEGRAM_BOT_USERNAME` | Mini App | Bot 1 username for helper links | `<BOT_USERNAME>` |
| `VITE_TELEMETRY_DISABLED` | Mini App | Disables frontend telemetry when `true` | `false` |
| `VITE_APP_VERSION` | Mini App | Optional build/version marker | `<VERSION>` |

Sensitive values that must never be committed or pasted into docs include bot tokens, DB passwords, JWT secrets, webhook secrets, Yandex Disk tokens, Sentry DSNs, private keys, production `.env` content, uploaded user files, backups, and database dumps.

## 5. Production Deployment Procedure

Always run and verify a backup before deploying migrations. Do not deploy migrations if the backup fails.

SSH and enter production path:

```bash
ssh tsplatform-frankfurt
cd /opt/telegram-shop
```

Pre-check:

```bash
git status --short
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
```

Backup:

```bash
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 160 --no-pager
```

Pull:

```bash
git fetch origin
git pull --ff-only origin main
```

Build:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml build backend mini-app seller-panel
```

Migrations:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend alembic upgrade head
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend alembic current
```

Restart:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml up -d backend mini-app seller-panel
```

Smoke checks:

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

Logs:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=250 backend
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 mini-app
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 seller-panel
```

Deploy variants:

- Backend-only deploy without migrations: build and restart `backend` only after confirming frontend assets and public API contracts do not need updates.
- Frontend-only Mini App deploy: build and restart `mini-app` only.
- Frontend-only Seller Panel deploy: build and restart `seller-panel` only.
- If migrations exist, run backup first and run Alembic before considering the deploy complete.

## 6. Backup Documentation

Production backup entry points:

- systemd service: `telegram-shop-backup.service`
- systemd timer: `telegram-shop-backup.timer`
- production path: `/opt/telegram-shop`
- backup script: `backend/scripts/backup_production.py`
- env file: `backend/.env.production`

Backups include PostgreSQL data, upload files, backup metadata, commit/migration metadata, and local/remote retention handling. The scheduled timer runs daily at 04:00 Moscow time. Every run creates a local backup; only every seventh successful local backup uploads to Yandex Disk.

Backup notifications:

- Route to `TELEGRAM_BACKUP_CHAT_ID`.
- Fall back to `TELEGRAM_SELLER_CHAT_ID` only as a legacy fallback.
- Must not be routed to orders or returns groups.
- Sent every run with local backup status and remote upload status (`skipped`, `sent`, or `failed`).

Restore verification:

- `BACKUP_RESTORE_VERIFY_ENABLED=true` enables restore verification in the backup script.
- Verification is implemented in `backend/scripts/backup_production.py` and validates backup integrity using an isolated restore check flow.

Useful commands:

```bash
sudo systemctl status telegram-shop-backup.timer --no-pager
sudo systemctl start telegram-shop-backup.service
sudo journalctl -u telegram-shop-backup.service -n 160 --no-pager
sudo systemctl cat telegram-shop-backup.service
```

Operational details:

- Run a backup before every migration deploy.
- Do not deploy migrations if the backup service fails.
- The service can run for several minutes.
- Yandex Disk upload may occasionally timeout and retry. If the seventh remote upload fails after retries, the next daily backup retries the pending remote upload.
- Use journal logs to confirm final success, not only the first status line.

## 7. Telegram Groups and Diagnostics

Desired Bot 2 group split:

| Group | Env variable | Purpose |
| --- | --- | --- |
| Orders group | `TELEGRAM_ORDERS_CHAT_ID` | Order notifications, seller/admin commands, manual payment callbacks, seller registration approval callbacks |
| Returns group | `TELEGRAM_RETURNS_CHAT_ID` | Return request notifications, attached return media, inline buttons `Подтвердить` / `Отклонить` |
| Backup group | `TELEGRAM_BACKUP_CHAT_ID` | Backup success/failure notifications only |

Behavior notes:

- Return media attachments are uploaded to Telegram as media files from stored bytes. Raw filesystem paths are not sent as customer-visible attachment content.
- Return callbacks require the Telegram actor to resolve to an active `SELLER` or `ADMIN` identity.
- Return callbacks are accepted only in the configured returns group.
- Orders commands and callbacks should not work in returns or backup groups.
- Telegram group topics/thread ids are not supported yet.

Diagnostics script:

```text
backend/scripts/telegram_diagnostics.py
```

Production diagnostic command:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend \
  python scripts/telegram_diagnostics.py --env-file .env.production
```

With test send:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend \
  python scripts/telegram_diagnostics.py --env-file .env.production --send
```

The script checks Bot 2 `getMe` and `getChat` for orders, returns, backup, and legacy seller chat ids. It prints whether the bot token is configured but does not print the token.

## 8. Product Behavior

Product statuses:

- `DRAFT`
- `ACTIVE`
- `OUT_OF_STOCK`
- `ARCHIVED`

`Product.is_listed`:

- When `false`, the product is hidden from public feed, category pages, search, tags, suggestions, and related products.
- A hidden product still opens by direct link if its status is `ACTIVE`.
- Hidden active products can be used inside Looks.

`Product.is_returnable`:

- Controls whether future purchases of a product can be returned.
- Snapshotted into `OrderItem.is_returnable` during checkout.
- Changing the product flag later does not mutate historical order item returnability.

`Product.size_group`:

- `CLOTHING`: clothing size selector behavior.
- `FOOTWEAR`: footwear size selector behavior.
- `ONE_SIZE`: no size selector required in Looks.

Product slug generation:

- Numeric slugs are generated in the range `00001` to `99999`.
- `00000` is never generated.
- Product slugs are globally unique in the product namespace.
- Generation and updates respect active product route aliases.

Variant SKU generation:

- Numeric SKUs are generated in the range `00001` to `99999`.
- `00000` is never generated.
- SKU aliasing is not implemented.

Public links:

- Product/category route: `/category/<category-slug>/product/<product-slug>`.
- SKU preselection: add `?sku=<variant-sku>`.
- Direct product route by id still exists in the Mini App for internal navigation: `/product/<product-id>`.
- Public resolvers canonicalize old category/product slugs through route aliases.

## 9. Looks / Outfits

Looks are independent entities, not Products. Looks do not have stock of their own.

Look fields:

- `slug`
- `title`
- `description`
- `status`
- `is_listed`
- `search_priority`
- custom images through `LookImage`
- product components through `LookItem`

Look statuses:

- `DRAFT`
- `ACTIVE`
- `ARCHIVED`

Look products:

- A LookItem references a Product.
- Hidden active products can be used in Looks.
- Archived products cannot be used for an active Look.
- Active Looks need at least one item and at least one default-selected item.

Look slug generation:

- Numeric Look slugs are generated in the range `00001` to `99999`.
- `00000` is never generated.
- Look slugs are unique in the Look namespace.
- Generation skips active `LOOK` route aliases.

Seller Panel Looks UI:

- List Looks.
- Create Looks.
- Edit Looks.
- Archive Looks.
- Manage product components.
- Mark default-selected items.
- Upload/delete Look images.
- Use automatic slug autofill.

Mini App Looks UI:

- Mixed feed cards on the main page.
- Dedicated `/looks` page.
- Look detail page at `/looks/:slug`.

Look size logic:

- Clothing and footwear size requirements are resolved independently.
- UI exposes separate selectors for `Размер одежды` and `Размер обуви` where both are needed.
- `ONE_SIZE` items require no selector.
- Clothing sizes are intersected across selected clothing items.
- Footwear sizes are intersected across selected footwear items.

Look add-to-cart:

- Endpoint: `POST /api/v1/looks/{slug}/cart`.
- Adds selected Look items only.
- Validates selected item ids, size requirements, variant availability, and stock before commit.
- Uses one `source_group_id` for the selected Look add operation.
- No partial add should persist on validation failure.

Cart/order grouping:

- Look-sourced cart and order items carry `source_type="LOOK"`, Look id, Look slug, Look title, Look image URL, and `source_group_id`.
- Cart, checkout, order detail, and Seller Panel order detail group these items.
- UI group label: `Куплено из образа: <Look title>`.

## 10. Mixed Feed

Endpoint:

```text
GET /api/v1/feed
```

Feed item types:

- `product`
- `look`

Rules:

- Product and Look remain separate models.
- Feed includes only `ACTIVE` plus listed products.
- Feed includes only `ACTIVE` plus listed Looks.
- Hidden standalone products do not appear.
- Hidden active products inside Looks are allowed because the Look is the public entity.
- Mini App main page uses the mixed feed.
- Dedicated Looks page still exists at `/looks`.

## 11. Route Aliases

Table:

```text
route_aliases
```

Entity types:

- `PRODUCT`
- `CATEGORY`
- `LOOK`

Behavior:

- Old slugs are automatically saved when a Product, Category, or Look slug changes.
- Public resolution tries the current slug first, then an active alias.
- Resolvers return canonical current slugs so the Mini App can replace old URLs with `history.replace`.
- Route aliases do not bypass status or visibility restrictions.

Supported old links:

- Old product slug.
- Old category slug.
- Old Look slug.
- Old category plus old product plus `sku` query.

Not implemented:

- SKU aliasing.
- Route alias admin UI.

## 12. Returns

Return creation:

- Allowed only after an order is `DELIVERED`.
- Uses a 14-day window from `orders.delivered_at` when available, otherwise from order creation.
- One return request per order.
- Partial returns are supported by item and quantity.
- Attachments are supported for return creation.
- Current validation allows up to 5 attachments, 20 MB each, with supported image/video MIME types.

Return statuses:

- `PENDING`
- `APPROVED`
- `REJECTED`
- `COMPLETED`
- `CANCELLED`

Allowed transitions:

- `PENDING -> APPROVED`
- `PENDING -> REJECTED`
- `PENDING -> CANCELLED`
- `APPROVED -> COMPLETED`
- `APPROVED -> CANCELLED`

Final statuses:

- `REJECTED`
- `COMPLETED`
- `CANCELLED`

Customer capabilities:

- Check return eligibility for an order.
- Create a return request for eligible delivered items.
- Attach return media.
- Cancel own `PENDING` return request.

Seller/admin capabilities:

- List and open return requests.
- Approve or reject pending requests.
- Cancel pending or approved requests.
- Complete approved requests.
- Process refund/restock details.

Telegram behavior:

- Return notifications go to the returns group.
- Media attachments are sent to Telegram.
- Inline buttons `Подтвердить` and `Отклонить` are available.
- Callback actions require an active `SELLER` or `ADMIN` Telegram identity.
- Callback actions are accepted only in the configured returns group.

Refund/restock:

- Manual only.
- No payment provider integration.
- No automatic money movement.
- Restock only happens by explicit seller/admin choice.
- Restock is delta-safe and avoids double restock by tracking already restocked quantity.
- Processing can record refund/restock and complete the return when requested.

## 13. Seller Panel

Current main pages and routes:

- `/dashboard`: operational dashboard.
- `/orders`: order list/detail, status management, manual payment visibility, grouped Look-source items.
- `/products`: product list.
- `/products/new`: product creation.
- `/products/:id/edit`: product editing.
- `/taxonomy`: categories and tags.
- `/banners`: banner management.
- `/promo-codes`: promo code management.
- `/reviews`: review moderation.
- `/returns`: return list/detail and lifecycle operations.
- `/looks`: Look list.
- `/looks/new`: Look creation.
- `/looks/:id/edit`: Look editing.
- `/statistics`: statistics where implemented.
- `/customer-notifications`: customer subscriptions/campaigns.
- `/channel-entry`: Bot 1 channel-entry publish/pin flow with up to four photos, button styles, preview, and history.
- `/seller-bot`: seller bot tools.
- `/settings`: implemented settings.

Product feature controls:

- `Показывать в витрине`: controls `Product.is_listed`.
- `Возвратный товар`: controls `Product.is_returnable`.
- `Тип размера`: controls `Product.size_group` as clothing, footwear, or one size.

Returns features:

- List/detail view.
- Approve/reject.
- Cancel/complete.
- Refund and restock processing.
- Attachment preview.
- Restock audit and refund audit display.

Looks features:

- List/create/edit/archive.
- Automatic slug autofill.
- Product components.
- Default-selected items.
- Hidden active product components.
- Image upload/delete.

## 14. Mini App

Current routes/features:

- `/` and `/main`: launch/main storefront.
- Main mixed feed with product and Look cards.
- `/categories`: category list.
- `/category/:slug`: category page.
- `/category/:categorySlug/product/:productSlug`: category/product link with alias resolution.
- `/product/:id`: direct product detail route.
- `/looks`: Looks list.
- `/looks/:slug`: Look detail route with alias canonicalization.
- `/search`: search entry.
- `/search/results`: search results.
- `/cart`: cart and order tabs.
- `/checkout`: checkout.
- `/payment/:orderId`: manual payment.
- `/order-success/:orderId`: order success/detail.
- `/orders/:orderId/return`: return request flow.
- `/profile`: profile/orders.
- `/profile/personal-data`: personal data.
- `/faq`: FAQ.

Mini App behavior:

- Direct links with route aliases are resolved and replaced with canonical URLs.
- Category/product links preserve SKU query selection when canonicalized.
- Look-sourced cart/order items are grouped.
- Looks support separate clothing and footwear size selectors.
- `ONE_SIZE` Look items require no selector.
- Returns flow supports eligible delivered orders and media attachments.

## 15. API Overview

Base prefix:

```text
/api/v1
```

High-level endpoint groups:

- `GET /products`: public product catalog list/search.
- `GET /products/suggestions`: public search suggestions.
- `GET /products/resolve`: product/category slug resolver with optional SKU.
- `GET /products/{product_id}` and `GET /products/{product_id}/variants`: public product detail/variants.
- `/products/admin...`: seller/admin product CRUD, slug generation, variant SKU generation, variants, status/archive.
- `GET /categories`, `GET /categories/resolve`, `/categories...`: taxonomy and category resolution/CRUD.
- `/tags...`: tags and tag CRUD.
- `GET /feed`: mixed feed of products and Looks.
- `GET /looks`, `GET /looks/{slug}`, `POST /looks/{slug}/cart`: public Looks.
- `/looks/admin...`: seller/admin Look list, slug generation, CRUD, images, archive.
- `/cart...`: customer cart, item selection, bulk selection, clear.
- `/orders/checkout`, `/orders`, `/orders/{id}`: customer checkout and orders.
- `/orders/admin...`: seller/admin orders, status changes, customer message sends.
- `/orders/{order_id}/return-eligibility`, `/orders/{order_id}/returns`, `/returns/{id}/cancel`: customer returns.
- `/returns/admin...`: seller/admin return list/detail/approve/reject/complete/process/cancel.
- `/promo-codes...`: promo code validation and seller/admin management.
- `/banners...`: public banners and seller/admin banner management.
- `/uploads...`: product, banner, category, tag, campaign, return, and receipt upload support where routed.
- `/customer-notifications...`: subscriptions, write access, start links, campaigns, templates, delivery reports.
- `/channel-entry...`: channel configuration, safe photo upload, preview, publish, pin, and history. Albums use `sendMediaGroup` plus a separate pinnable entry message.
- `/seller-auth...`, `/seller-bot...`, `/telegram...`: seller auth and Telegram webhook/tooling endpoints.

This is an overview only. Use backend OpenAPI at `/api/v1/openapi.json` for exact request/response schemas.

## 16. Testing and QA

Standard local checks for a full release candidate.

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -X pycache_prefix=tmp\compileall_cache -m compileall app tests scripts
.\.venv\Scripts\ruff.exe check . --no-cache
.\.venv\Scripts\pytest.exe -W error -o cache_dir=tmp\pytest_cache
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

Manual smoke scenarios:

- Hidden product does not appear in feed/category/search/tag/suggestions/related lists but opens by direct link when `ACTIVE`.
- Return with media creates a request, sends attachments to returns Telegram group, and supports Telegram approve/reject.
- Seller/admin refund/restock processing records refund details, updates restock quantities, and avoids double restock.
- Look containing clothing and footwear products requires independent clothing and footwear selectors.
- Look add-to-cart groups selected components in cart, checkout, order detail, and Seller Panel order detail.
- Old product/category/Look links resolve and replace with canonical URLs.
- Mixed feed shows product and Look cards.
- Backup service sends backup notifications to backup group and completes successfully in journal logs.

## 17. Known Limitations and Future Work

- No automatic payment-provider refunds.
- No automatic restock without seller/admin choice.
- No SKU aliasing.
- Telegram group topics/thread IDs are not supported yet.
- Route alias admin UI is not implemented.
- Looks are not Products and do not have stock of their own.
- Backup depends on Yandex Disk availability and may retry on timeouts.
- Vite build chunk-size warnings may appear; they are not deployment blockers when the build passes.

## 18. Migration History Summary

Current production head after the latest release:

```text
20260703_0047
```

Recent migrations:

| Revision | Operational summary |
| --- | --- |
| `20260701_0040` | Added product visibility (`is_listed`), product returnability (`is_returnable`), `OrderItem.is_returnable`, and `orders.delivered_at`. |
| `20260701_0041` | Added return request tables, return request items, return request attachments, initial return statuses, and one-return-per-order constraint. |
| `20260702_0042` | Added Looks, Look images, LookItems, Look statuses, public listing fields, and Look listing indexes. |
| `20260702_0043` | Added return lifecycle statuses `COMPLETED` and `CANCELLED`, plus completed/cancelled audit fields. |
| `20260702_0044` | Added return refund records and restock audit fields on return request items. |
| `20260703_0045` | Added Look source grouping to cart and order items for grouped cart/order display. |
| `20260703_0046` | Added route aliases for Product, Category, and Look slugs. |
| `20260703_0047` | Added `Product.size_group` with clothing, footwear, and one-size behavior. |

## 19. Related Documentation

- `README.md`: project entry point and documentation map.
- `docs/ARCHITECTURE.md`: component architecture and backend boundaries.
- `docs/ENVIRONMENT.md`: environment variable reference.
- `docs/PRODUCTION_DEPLOYMENT.md`: production deploy runbook.
- `docs/OPERATIONS.md`: routine production operations.
- `docs/BACKUP_AND_RESTORE.md`: backup and restore procedures.
- `docs/BACKUP_STRATEGY.md`: backup strategy, retention, and verification.
- `docs/TESTING.md`: required checks by area.
- `UI_DESIGN_SPEC.README.md`: Mini App and Seller Panel design rules.

## Transactional Outbox Handover

The current migration head is `20260711_0053`. Order created/promo/status/shipped events and
manual-payment submitted/approved/rejected/expired events are enqueued atomically and processed
by the backend lifespan worker. Operational status is available through the authorized outbox
diagnostics endpoint; payloads are deliberately excluded. Analytics remains best-effort, and
return-request notification remains direct post-commit. Delivery is at-least-once, not exactly
once at Telegram's external boundary.
