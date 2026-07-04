# Software Requirements Summary - StyleXac

This document is the current software requirements summary for TelegramShopPlatform / StyleXac.

## Product Goal

StyleXac is a Telegram-native commerce platform for selling products through a customer Mini App and operating the catalog, orders, promotions, banners, campaigns, and channel entry through a Seller Panel.

## Current Production Context

| Area | Value |
| --- | --- |
| Main domain and Mini App entry | `https://stylexac.ru` |
| Mini App direct domain | `https://mini.stylexac.ru` |
| API domain | `https://api.stylexac.ru` |
| Seller Panel domain | `https://seller.stylexac.ru` |
| Server | Aeza Frankfurt |
| Production path | `/opt/telegram-shop` |
| Production compose | `docker-compose.prod.yml` |
| Production env | `backend/.env.production` |
| Current migration head | `20260703_0047` |

## Actors

| Actor | Description |
| --- | --- |
| Customer | Uses Telegram Mini App, browses products, adds to cart, checks out, receives service notifications |
| Seller | Manages products, variants, banners, promo codes, orders, customer notifications, and channel entry |
| Admin | Has elevated seller/admin access and can perform critical actions |
| Bot 1 | Customer-facing Telegram bot |
| Bot 2 | Seller/admin/auth-related Telegram bot |

## Roles

Backend roles:

- `USER`
- `SELLER`
- `ADMIN`

Seller/admin routes must enforce the correct role. Customer Mini App routes must use authenticated Telegram users where required.

## Functional Requirements

### Auth and Users

- The Mini App authenticates with Telegram `initData`.
- Backend validates Telegram signature and `auth_date` server-side.
- Backend upserts users from Telegram payload.
- Backend issues JWT sessions after successful Telegram auth.
- Mini App waits for `Telegram.WebApp.initData`, deduplicates login, coordinates `401` refresh, and retries once after refresh.
- Raw `initData` must not be stored or logged.

### Catalog

- Sellers/admins can manage categories, tags, products, images, variants, prices, `old_price`, inventory, active/public visibility, returnability, size groups, and search metadata.
- Products can belong to multiple categories with priority values `1`, `2`, and `3`.
- Search supports aliases, priority, color synonym expansion, and typo tolerance through PostgreSQL `pg_trgm` when available.
- Mini App product detail displays brand above title.
- Hidden active products do not appear in public lists but remain available by direct link and can be used inside Looks.
- Product returnability is snapshotted into order items during checkout.

### Feed, Looks, and Route Aliases

- The main Mini App feed uses `GET /api/v1/feed` and can contain product and Look items.
- Looks are independent outfit entities with custom images and product components.
- Looks do not have stock of their own.
- Look add-to-cart validates selected items, independent clothing/footwear sizes, and stock before committing grouped cart items.
- Cart, checkout, order detail, and Seller Panel order detail group Look-sourced items.
- Product, category, and Look slug changes create route aliases so old public links continue resolving to canonical current URLs.
- SKU aliasing is not implemented.

### Cart and Checkout

- Customers can add product variants to cart.
- Cart totals are calculated by backend.
- Promo codes can be applied before checkout.
- Checkout creates an order transactionally.
- Stock is checked and decremented inside checkout.
- `OrderItem` stores immutable purchased-product snapshots.
- Notifications are emitted only after successful persistence.
- Cart UI displays: `Цена сформирована без учёта стоимости доставки.`
- Product detail UI displays: `Мы подбираем размер по росту и весу.`

### Orders

- Orders have statuses managed by backend services.
- Status changes create audit logs where required.
- Customer and seller notifications are emitted after status persistence.
- Order items must remain snapshots even if product data changes later.
- Delivered orders record `delivered_at` for return-window calculation.

### Returns

- Returns are allowed only after `DELIVERED` orders and within a 14-day window.
- One return request is allowed per order.
- Partial returns and media attachments are supported.
- Return statuses are `PENDING`, `APPROVED`, `REJECTED`, `COMPLETED`, and `CANCELLED`.
- Customers can create eligible return requests and cancel own pending requests.
- Seller/admin users can approve, reject, cancel, complete, and process manual refund/restock details.
- Return Telegram notifications go to the returns group with approve/reject buttons.
- Refunds are recorded manually; no automatic payment-provider refund exists.
- Restock requires explicit seller/admin choice.

### Promo Codes

- Promo codes support percentage and fixed discounts.
- Promo codes support usage limits and per-user limits.
- Checkout records coupon usage snapshots through `CouponUsage`.

### Uploads

- Supported upload classes: product images, banner images, category images, tag images, review images, customer campaign images, manual payment receipts.
- Backend validates size, extension, MIME, image decoding, safe filenames, path containment, and aspect ratio where an image profile exists.
- PostgreSQL stores paths/URLs only.

### Banners

- Banner display types: `horizontal`, `vertical`, `popup`, `aggressive_popup`.
- Implemented crop profiles:
  - horizontal native banner: `400:207`
  - vertical: `9:16`
  - popup: `3:4`
  - aggressive popup: `9:16`
- Aggressive popup can appear on Mini App entry.
- Banner view/click analytics are captured where implemented.

### Customer Notifications

- Bot 1 owns customer notification flows.
- `CustomerTelegramSubscription` tracks real chat state, opt-ins, write-access state, blocked state, and delivery errors.
- Bot 1 `/start` creates or updates real private chat subscription state.
- Bot 1 `/stop` disables service and marketing eligibility.
- Mini App write access is requested only after user action.
- Write-access result is persisted through `POST /api/v1/customer-notifications/me/write-access`.
- Write access enables service notifications without enabling marketing.
- Service sends prefer `telegram_chat_id`; if no real private chat exists, current logic can use `telegram_user_id` when write access is granted.
- Campaign delivery requires real private Bot 1 chat and eligible opt-in state.
- Campaigns support images, preview, test send, delivery status, and reports.

### Telegram Channel Entry

- Seller Panel route `/channel-entry` publishes a channel message through Bot 1.
- Channel message button uses a URL to Mini App `startapp`.
- Default link: `https://t.me/CheckYouStyleBot?startapp=channel_pin`.
- If `TELEGRAM_MINI_APP_SHORT_NAME` exists, direct link builder may use the short-name path.
- Channels use URL buttons, not `web_app` buttons.
- History stores Telegram `message_id`, pin status, publish status, and sanitized errors.
- Channel-entry `initData` auth creates or updates a `User`, but does not create real private Bot 1 chat state.

### Mini App

- Mobile-first marketplace-style experience.
- Implemented flows: mixed feed, category, search, product detail, Looks list/detail, cart, profile, checkout, order detail, returns.
- Floating help widget `Как совершить заказ?` appears on feed/category/search, is draggable, can be hidden/swiped to side, leaves a side tab, and restores on tab tap.
- Cart promo input is keyboard-safe.
- Bottom navigation is optimized for Telegram WebView.
- Discount badge visual tiers: `1-20%`, `21-40%`, `41-60%`, `61-80%`, `81-99%`.

### Seller Panel

- Desktop-first dashboard-style experience.
- Implemented areas: products, variant matrix, image uploads, orders, returns, Looks, banners, promo codes, customer notifications, channel entry, seller/admin auth-related flows, badge preview where present.
- Seller Panel domain: `https://seller.stylexac.ru`.

## Non-Functional Requirements

### Reliability

- Checkout must be transactional.
- Notifications must follow persistence.
- Backup must run before migrations.
- Production smoke checks must cover API, Mini App, and Seller Panel.

### Security

- Never expose real secrets in docs or logs.
- Validate Telegram `initData` server-side.
- Keep Bot 1 and Bot 2 responsibilities separated.
- Enforce seller/admin roles.
- Validate uploads.
- Do not store uploaded file bytes in PostgreSQL.

### Operations

- Production deploy uses `docker-compose.prod.yml` and `backend/.env.production`.
- Production backup uses `telegram-shop-backup.service`.
- Caddy HTTP/3/QUIC is intentionally disabled.
- `tsplatform-mss-clamp.service` is intentionally enabled with TCPMSS `set-mss 1120` for ports `80` and `443`.

## Required Checks

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
