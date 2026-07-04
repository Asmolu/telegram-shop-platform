# TelegramShopPlatform / ICON STORE

TelegramShopPlatform / ICON STORE is a production Telegram commerce platform: a customer Telegram Mini App, a desktop Seller Panel, a FastAPI backend, and two Telegram bots with separated responsibilities. The current production domain family is `stylexac.ru`.

The repository is documentation-driven and module-oriented. Backend routers stay thin, services own business rules and transactions, repositories own SQLAlchemy queries, and PostgreSQL is the source of truth.

## Production State

| Area | Current value |
| --- | --- |
| Main domain and Mini App entry | `https://stylexac.ru` |
| Mini App direct domain | `https://mini.stylexac.ru` |
| API domain | `https://api.stylexac.ru` |
| Seller Panel domain | `https://seller.stylexac.ru` |
| Server | Aeza Frankfurt |
| Operational SSH alias | `tsplatform-frankfurt` |
| Production path | `/opt/telegram-shop` |
| Production compose file | `docker-compose.prod.yml` |
| Production env file | `backend/.env.production` |
| Current migration head | `20260703_0047` |

Reverse proxying is handled by host Caddy. HTTP/3/QUIC is intentionally disabled, and `tsplatform-mss-clamp.service` is intentionally enabled to improve Telegram WebView, VPN, and MTU compatibility.

## Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2.0 async ORM, Alembic, Pytest, Ruff |
| Data stores | PostgreSQL 16, Redis 7 |
| Mini App | React, Vite, TypeScript |
| Seller Panel | React, Vite, TypeScript |
| Bot 1 | Customer-facing bot for `/start`, `/stop`, service notifications, campaigns, and channel entry publication |
| Bot 2 | Seller/admin/auth-related bot flows |
| Uploads | Local filesystem paths served through backend and reverse proxy |
| Deployment | Docker Compose production stack: backend, postgres, redis, mini-app, seller-panel |

## Implemented Product Areas

### Auth and Users

- Telegram Mini App `initData` login with server-side signature and age validation.
- Backend JWT session after Telegram auth.
- User upsert from Telegram user payload.
- Roles: `USER`, `SELLER`, `ADMIN`.
- Mini App waits for `Telegram.WebApp.initData`, deduplicates in-flight login, coordinates API `401` refresh, and retries once after refresh.
- Auth diagnostics are sanitized. Raw `initData`, bot tokens, JWT secrets, and production credentials must never be logged or documented.

### Catalog

- Categories, tags, products, product images, variants, inventory, product status, active/public visibility, returnability, size groups, and `old_price`.
- Search priority, search aliases, color synonym expansion, and typo-tolerant search through PostgreSQL `pg_trgm` when the extension is available.
- Multi-category product assignments with priority values `1`, `2`, and `3`.
- Product brand is displayed above the title in the Mini App product detail view.
- `Product.is_listed=false` hides a product from public lists while keeping direct links available when the product is `ACTIVE`.
- `Product.is_returnable` is snapshotted into `OrderItem.is_returnable` during checkout.
- Product slugs and variant SKUs can be generated as numeric identifiers from `00001` to `99999`; `00000` is never generated.

### Mixed Feed, Looks, and Route Aliases

- `GET /api/v1/feed` returns mixed product and Look feed items for the Mini App main page.
- Looks are independent outfit entities with custom images and LookItems referencing Products.
- Active hidden products can be used inside Looks, but Looks do not have stock of their own.
- Look add-to-cart validates selected components and independent clothing/footwear sizes before committing grouped cart items.
- Cart, checkout, order detail, and Seller Panel order detail group Look-sourced items with `Куплено из образа: <Look title>`.
- Product, category, and Look slug changes create `RouteAlias` rows so old public links continue resolving to canonical current URLs.
- SKU aliasing is not implemented.

### Cart, Checkout, and Orders

- Cart items and totals.
- Promo code validation and application during checkout.
- Order creation is transactional.
- Product variant stock is checked and decremented inside checkout.
- `OrderItem` stores an immutable purchased-product snapshot: product id, variant id, product name, size, grid, color, SKU, unit price, quantity, and subtotal.
- Order status changes create audit entries and emit notifications only after successful persistence.
- Delivered orders record `delivered_at`, which is used by the return window.
- Current Mini App copy:
  - Cart: `Цена сформирована без учёта стоимости доставки.`
  - Product detail: `Мы подбираем размер по росту и весу.`

### Promo Codes

- Percentage and fixed-amount discounts.
- Usage limits, per-user limits, active windows, and checkout integration.
- `CouponUsage` records redemption snapshots.

### Returns

- Return requests are available only after `DELIVERED` orders, within a 14-day window.
- One return request is allowed per order, with partial item quantities and media attachments.
- Statuses are `PENDING`, `APPROVED`, `REJECTED`, `COMPLETED`, and `CANCELLED`.
- Seller/admin users can approve, reject, cancel, complete, and process refund/restock details.
- Refunds are recorded manually; there is no automatic payment-provider refund.
- Restock happens only by explicit seller/admin choice and is delta-safe.
- Return notifications go to the returns Telegram group with media attachments and approve/reject buttons.

### Uploads

- Product images, banner images, category images, tag images, review images, customer campaign images, and manual payment receipts.
- Size, extension, MIME, image decoding, aspect-ratio validation where a profile exists, safe filenames, and path containment.
- PostgreSQL stores file paths and URLs only. Uploaded binary files are not stored in the database.

### Banners

- Display types: `horizontal`, `vertical`, `popup`, `aggressive_popup`.
- Current implemented crop profiles:
  - horizontal native banner: `400:207`
  - vertical: `9:16`
  - popup: `3:4`
  - aggressive popup: `9:16`
- Aggressive popup is used as an entry overlay in the Mini App.
- Banner view and click events are captured through analytics when relevant.

### Customer Notifications

- `CustomerTelegramSubscription` tracks `service_opt_in`, `marketing_opt_in`, `has_chat`, `chat_type`, `telegram_chat_id`, `telegram_user_id`, `blocked_at`, write-access fields, and delivery errors.
- Bot 1 `/start` creates or updates a real private-chat subscription.
- Bot 1 `/stop` disables service and marketing eligibility according to current backend logic.
- Mini App write access is requested only after a user action through `requestWriteAccess()`.
- `POST /api/v1/customer-notifications/me/write-access` persists write-access state.
- Granted write access enables service notifications without silently enabling marketing.
- Service notification sending prefers `telegram_chat_id` when a real private chat exists; otherwise it can use `telegram_user_id` when `write_access_granted=true`.
- Campaigns support images, previews, test sends, delivery reports, and status management. Campaign delivery requires a real private Bot 1 chat.
- Template tables and backend endpoints exist; the Seller Panel UI is currently simplified around campaign creation and delivery operations.

### Telegram Channel Entry

- Seller Panel route: `/channel-entry`.
- Bot 1 publishes and optionally pins a channel message.
- Channel button uses a URL to Mini App `startapp`: `https://t.me/CheckYouStyleBot?startapp=channel_pin`.
- When `TELEGRAM_MINI_APP_SHORT_NAME` is configured, the direct link builder can use the short-name path.
- Channels must use a URL button, not a Telegram `web_app` button.
- History stores Telegram `message_id`, pin status, publish status, and sanitized errors.
- Channel-entry auth via `initData` creates or updates a `User`, but does not by itself create a real private Bot 1 chat. The write-access flow is the service-notification path for those users.

### Mini App

- Mobile-first marketplace layout with feed, category, search, product, cart, profile, and checkout flows.
- Floating help widget `Как совершить заказ?` appears on feed/category/search, is draggable, can be hidden or swiped to the screen side, leaves a side tab, and restores on tab tap.
- Cart promo input is keyboard-safe in Telegram WebView.
- Discount badge tiers are implemented for `1-20%`, `21-40%`, `41-60%`, `61-80%`, and `81-99%`, with configurable visual sizing.
- Bottom navigation is built for Telegram mobile WebView constraints.

### Seller Panel

- Product management, variant matrix, product image uploads, banner management, promo codes, customer notifications, channel entry publishing, seller/admin auth flows, and badge preview where product-image badges are edited.
- The Seller Panel is desktop-first and dashboard-like. It must not visually mirror the Mini App.

## Local Development

`.env` is for local development and local checks. `backend/.env.production` is for VDS/server work and production-domain checks only. Do not put real production secrets in documentation.

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

If the local host does not have Python, Ruff, Pytest, or PostgreSQL-compatible services, run backend checks inside the backend Docker container.

## Documentation Map

| File | Purpose |
| --- | --- |
| `docs/PROJECT_HANDOVER.md` | Comprehensive current production handover for developers/operators |
| `docs/ARCHITECTURE.md` | Components, modules, data flows, backend boundaries |
| `docs/ENVIRONMENT.md` | Environment variables and safe placeholder conventions |
| `docs/PRODUCTION_DEPLOYMENT.md` | Production deploy, migrations, smoke checks, logs, rollback |
| `docs/OPERATIONS.md` | Routine production operations, backups, Caddy, MTU, diagnostics |
| `docs/BACKUP_AND_RESTORE.md` | Backup and restore procedures |
| `docs/BACKUP_STRATEGY.md` | Backup policy, retention, and verification |
| `docs/CUSTOMER_NOTIFICATIONS_ARCHITECTURE.md` | Bot 1 subscriptions, write access, service sends, campaigns |
| `docs/TELEGRAM_CHANNEL_ENTRY.md` | Channel entry publication and Mini App start parameter flow |
| `docs/TESTING.md` | Required checks by area |
| `docs/LOCAL_DEVELOPMENT.md` | Local setup and development commands |
| `docs/CODEX_WORKFLOW.md` | Repository workflow for AI coding agents |
| `docs/ANALYTICS_TELEMETRY.md` | Analytics and telemetry behavior |
| `docs/SECURITY_REVIEW.md` | Current security review notes |
| `UI_DESIGN_SPEC.README.md` | Mini App and Seller Panel UI rules |
| `SRS.README.md` | Current software requirements summary |
| `SPRINT_PLAN.md` | Historical sprint record and current scope notes |

## Security Rules

- Never commit `.env`, production secrets, bot tokens, JWT secrets, DB passwords, Yandex Disk tokens, private keys, uploaded user files, database dumps, or credentials.
- Use placeholders in docs: `<SECRET>`, `<BOT_TOKEN>`, `<DATABASE_URL>`, `<JWT_SECRET>`.
- Bot 1 and Bot 2 responsibilities must stay separated.
- Telegram `initData` must always be validated server-side.
- Raw `initData` must not be logged or stored.
