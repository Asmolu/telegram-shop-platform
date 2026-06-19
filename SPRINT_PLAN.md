# Sprint Plan — Telegram Shop Platform

## Project Overview

Telegram Shop Platform — модульная e-commerce система для продаж через Telegram Mini App и отдельную Seller Panel.

Система состоит из:

- Telegram Mini App — клиентский интерфейс для покупателей;
- Seller Panel — web-панель продавца/администратора;
- Python Backend API — FastAPI + SQLAlchemy + Alembic;
- PostgreSQL — основной источник истины;
- Redis — кэш, очереди, фоновые задачи;
- Local File Storage `/uploads` — MVP-хранилище файлов с возможностью миграции в S3/R2.

Architecture type: **Modular Monolith (FastAPI)**.

---

## Development Strategy

Проект разрабатывается вертикальными срезами: каждый sprint должен давать рабочий инкремент системы, а не просто набор отдельных слоёв.

### Core principles

- PostgreSQL является источником истины для бизнес-данных.
- SQLAlchemy models + Alembic migrations являются источником истины для схемы БД.
- FastAPI routers не содержат бизнес-логику: только HTTP input/output.
- Бизнес-логика находится в `services`.
- Доступ к БД изолирован в `repositories` или query-функциях модуля.
- Pydantic schemas используются для request/response DTO.
- Telegram — только UI/transport layer, не источник данных.
- Заказ всегда сначала сохраняется в PostgreSQL, и только потом отправляются уведомления.
- File storage остаётся абстракцией: local сейчас, S3/R2 позже.
- Frontend получает контракт через OpenAPI, а не через общий TypeScript backend-код.

---

# Sprint 0 — Python Backend Infrastructure

## Goal
Поднять backend-основу под FastAPI.

## Backend

- FastAPI application setup.
- Uvicorn development server.
- Pydantic Settings configuration.
- PostgreSQL connection через SQLAlchemy async engine.
- Alembic initialization.
- Redis connection layer.
- Global exception handling.
- CORS configuration для Mini App и Seller Panel.
- `/health` endpoint.

## Storage

- Local `/uploads` structure.
- Static file serving для uploaded files.
- Storage service abstraction.

## DevOps

- Backend Dockerfile.
- Docker Compose для backend + postgres + redis.
- `.env.example` для локального запуска.
- Basic pytest setup.

## Result
Backend запускается, подключается к PostgreSQL/Redis, отдаёт `/health`, готов к миграциям и загрузке файлов.

---

# Sprint 1 — Authentication & Users

## Goal
Сделать Telegram-based authentication и базовую модель пользователей.

## Features

- `User` model.
- `UserRole`: USER / SELLER / ADMIN.
- Telegram `initData` validation.
- JWT access token.
- Current user dependency.
- Role-based access control.
- Seller/Admin separation.

## Backend modules

- `auth`
- `users`

## Result
Пользователь может авторизоваться через Telegram Mini App, backend создаёт/обновляет профиль и выдаёт JWT.

---

# Sprint 2 — Product Catalog Core

## Goal
Создать базовый каталог товаров.

## Features

- `Product` CRUD.
- `Category` CRUD.
- `Tag` CRUD.
- Product status lifecycle: DRAFT / ACTIVE / OUT_OF_STOCK / ARCHIVED.
- Product list endpoint with pagination.
- Product detail endpoint.
- Filtering by category, tag, status.

## Backend modules

- `products`
- `categories`
- `tags`

## Result
Seller/Admin может управлять товарами, Mini App может получать публичный каталог.

---

# Sprint 3 — Uploads & Product Images

## Goal
Подключить загрузку и выдачу изображений.

## Features

- `ProductImage` model.
- Upload endpoint для изображений товаров.
- Upload endpoint для баннеров.
- File validation: size, extension, mime-type, decoded dimensions, pixel bounds, and aspect ratio.
- Local storage path persistence.
- Static serving `/uploads/*`.
- Seller Panel crop/fit editor before product and banner image upload.

Image standards:

- Product card/detail images: 4:5, recommended 1200x1500, minimum 600x750, maximum 1600x2000.
- Native banners: 400:207, recommended 2000x1035, minimum 1200x621, maximum 2400x1242.
- Aggressive popup banners: 9:16, recommended 900x1600, minimum 450x800, maximum 1350x2400.

## Backend modules

- `uploads`
- `products`
- `banners`

## Result
Товары и баннеры могут иметь изображения, в БД хранится только путь к файлу.

---

# Sprint 4 — Product Variants & Inventory

## Goal
Добавить реалистичную складскую модель для одежды.

## Features

- `ProductVariant` model.
- Size-based stock management: S / M / L / XL / custom.
- SKU field.
- Availability logic.
- Reserved stock field или подготовка под него.
- Запрет checkout при нехватке остатков.

## Backend modules

- `products`
- `orders`

## Result
Один товар может иметь несколько размеров/вариантов с разными остатками.

---

# Sprint 5 — Cart System

## Goal
Сделать постоянную корзину пользователя.

## Features

- `Cart` model.
- `CartItem` model.
- Add item to cart.
- Remove item from cart.
- Update quantity.
- Clear cart.
- Cart totals calculation.
- Validation against product status and variant stock.

## Backend modules

- `cart`

## Result
Пользователь может собрать заказ в корзине, корзина хранится в PostgreSQL.

---

# Sprint 6 — Orders Core Commerce

## Goal
Сделать полный checkout flow.

## Features

- `Order` model.
- `OrderItem` immutable snapshot.
- OrderStatus lifecycle: NEW / PROCESSING / SHIPPED / DELIVERED / CANCELLED.
- Stock deduction on checkout.
- Price snapshot at purchase time.
- Contact data and delivery fields.
- Transaction-safe order creation.
- Seller notification event after DB commit.

## Backend modules

- `orders`
- `cart`
- `notifications`
- `telegram`

## Result
Пользователь может оформить заказ, продавец получает уведомление, остатки корректно списываются.

---

# Sprint 7 — Promo Codes

## Goal
Добавить систему скидок.

## Features

- `PromoCode` model.
- `CouponUsage` model.
- Percentage discount.
- Fixed discount.
- Usage limits.
- User usage limits.
- Active date range.
- Promo validation during cart/checkout.

## Backend modules

- `promo_codes`
- `cart`
- `orders`

## Result
Промокоды применяются к заказу, история использования фиксируется.

---

# Sprint 8 — Reviews & Favorites

## Goal
Добавить social trust layer.

## Features

- `Review` model.
- `ReviewStatus`: PENDING / APPROVED / REJECTED.
- Review only after purchase.
- Review moderation by seller/admin.
- `Favorite` model.
- Add/remove favorites.
- Public approved reviews on product page.

## Backend modules

- `reviews`
- `favorites`
- `orders`

## Result
Покупатели могут сохранять товары и оставлять отзывы после покупки.

---

# Sprint 9 — Seller Panel Core API

## Goal
Закрыть основные backend API для Seller Panel.

## Features

- Product management API.
- Variant and stock management API.
- Order management API.
- Banner management API.
- Promo code management API.
- Review moderation API.
- Seller/Admin authorization guards.

## Backend modules

- `products`
- `orders`
- `banners`
- `promo_codes`
- `reviews`
- `users`

## Result
Seller Panel получает полный набор API для управления магазином.

---

# Sprint 10 — Notifications System

## Goal
Сделать event-based communication.

## Features

- `Notification` model.
- Internal event names: `order.created`, `order.shipped`, `product.updated`, `promo.used`.
- Telegram Bot API integration.
- User-facing notifications.
- Seller notifications.
- Redis queue подготовка для фоновой отправки.

## Backend modules

- `notifications`
- `telegram`
- `events`
- `jobs`

## Result
Система может отправлять уведомления без привязки бизнес-логики к Telegram API.

---

# Sprint 11 — Analytics & Audit

## Goal
Добавить наблюдаемость действий пользователей и продавцов.

## Features

- `AnalyticsEvent` model.
- `AuditLog` model.
- Tracking events:
  - product.viewed
  - cart.item_added
  - checkout.started
  - order.created
  - promo.used
- Admin action audit:
  - product.created
  - product.updated
  - banner.created
  - promo.updated
  - order.status_changed
- Basic reporting API.

## Backend modules

- `statistics`
- `audit`
- `analytics`

## Result
Есть базовая аналитика и журнал критических действий.

---

# Sprint 12 — Seller Panel UI Integration

## Goal
Подключить Seller Panel к реальному Python API.

## Features

- OpenAPI-based client generation или typed API wrapper.
- Product management UI.
- Order dashboard.
- Promo/banners UI.
- Review moderation UI.
- Error states and loading states.

## Frontend modules

- `seller-panel/src/shared/api`
- `seller-panel/src/pages/*`
- `seller-panel/src/features/*`

## Result
Seller Panel становится рабочим интерфейсом управления магазином.

---

# Sprint 13 — Mini App UX Completion

## Goal
Довести пользовательский Telegram Mini App до production-ready состояния.

## Features

- Catalog UX improvements.
- Product page UX.
- Horizontal size selector and manually managed related-products carousel.
- Configurable product image badges.
- Cart UX.
- Checkout flow.
- Promo code UI.
- Favorites UI.
- Reviews UI.
- Profile/orders page.
- Shared gradient headers for feed, cart, and profile plus aligned five-item footer icons.
- Telegram theme adaptation.

## Frontend modules

- `mini-app/src/pages/*`
- `mini-app/src/features/*`
- `mini-app/src/widgets/*`

## Result
Покупатель может пройти полный путь от каталога до заказа внутри Telegram Mini App.

---

# Sprint 14 — Production Hardening

## Goal
Подготовить систему к эксплуатации.

## Features

- Redis caching for hot catalog endpoints.
- Rate limiting.
- Structured logging.
- Error monitoring preparation.
- Pagination everywhere.
- DB indexes review.
- Alembic migration discipline.
- Docker production profile.
- Backup strategy for PostgreSQL and uploads.
- Security review.

## Result
Система готова к MVP production deployment.

## Sprint 14 delivery notes

- Added Redis-backed cache helpers for public catalog, taxonomy, banners, and approved reviews with service-level invalidation.
- Added configurable rate limiting, structured request logging, and error-monitoring placeholders.
- Added a new Alembic migration for missing production indexes.
- Added `docker-compose.prod.yml`, production env examples, and static frontend production containers.
- Added production deployment, backup/restore, and security review documentation.
- Documented remaining MVP limitations instead of changing existing API response shapes.

---

# Sprint 15 вЂ” Seller Portal Auth and Bot Management

## Goal
Р—Р°РјРµРЅРёС‚СЊ РІСЂРµРјРµРЅРЅС‹Р№ JWT-login РІ Seller Panel РЅР° email/password auth СЃ
Telegram Bot 2 verification Рё РґРѕР±Р°РІРёС‚СЊ СЃС‚СЂР°РЅРёС†Сѓ СѓРїСЂР°РІР»РµРЅРёСЏ Bot 2.

## Backend

- `seller_auth` module with pending registrations and seller credentials.
- Bot 2 start-token verification flow with hashed passwords, hashed tokens, and expiring hashed codes.
- Seller registration approval flow before code delivery with `PENDING`,
  `AWAITING_APPROVAL`, `APPROVED`, `REJECTED`, `EXPIRED`, and `VERIFIED`
  registration states.
- Bot 2 Telegram webhook at `/api/v1/telegram/seller-bot/webhook/<secret>`
  protected by `TELEGRAM_SELLER_WEBHOOK_SECRET`.
- `seller_bot` module for Bot 2 status, seller-chat test messages, seller-chat MVP broadcast, recent Telegram message listing, `/sellers`, and safe seller blocking through `/block_seller <user_id>`.
- Alembic migration `20260601_0013_add_seller_auth_tables.py`.
- Rate limiting for seller registration, login, verification, resend, and start-link callback endpoints.
- Audit entries for seller bot management actions.

## Frontend

- Seller Panel login/registration screen with email/password auth and Bot 2 verification code confirmation.
- Development-only JWT fallback remains hidden from production builds.
- Protected Seller Bot management page with labels that target the seller notification chat only.

## Result
Seller Portal can authenticate sellers without using Mini App Bot 1, and Bot 2 management is available without exposing bot tokens to the frontend.

---

# Sprint 16 - Customer Notifications MVP Phase 1

## Goal
Add the customer-facing Bot 1 subscription registry and customer notification
settings without adding campaigns, mass sending, or broadcast delivery.

## Backend

- `CustomerTelegramSubscription` model and Alembic migration for Bot 1
  private-chat state, consent flags, timestamps, and masked listing metadata.
- Bot 1 webhook at `/api/v1/telegram/customer-bot/webhook`, protected by
  `TELEGRAM_CUSTOMER_WEBHOOK_SECRET`.
- `/start`, `/settings`, `/stop`, and consent callback handling for service and
  marketing preferences.
- Mini App authenticated APIs for current-customer subscription state, opt-in
  updates, and Bot 1 start links.
- Seller/Admin read-only registry endpoint for subscription listing.
- Audit entries when customer notification settings change.

## Frontend

- Mini App Profile notification settings card with Bot 1 open-link action and
  consent toggles.
- Seller Panel customer notification registry page with filters and pagination.
- No campaign creation, send controls, or broadcast UI.

## Result
Customers can connect a private Bot 1 chat, manage notification consent, and
sellers/admins can inspect the subscription registry without exposing raw chat
IDs or bot secrets.

## Phase 1.5 delivery notes

- Customer-facing service notifications for order events are sent through Bot 1
  with `TELEGRAM_CUSTOMER_BOT_TOKEN` only after checkout/status transactions
  commit.
- `CustomerServiceNotificationDelivery` records service delivery attempts,
  skipped eligibility states, sanitized Telegram errors, and blocked/rate-limit
  outcomes.
- Bot 2 seller registration, seller verification, seller chat operations, and
  seller notifications remain separate.
- Marketing campaigns, mass sending, scheduling, `BroadcastCampaign`,
  `BroadcastDelivery`, campaign APIs, and campaign UI remain out of scope.

## Phase 2 delivery notes

- Added Bot 1 customer campaign infrastructure with `NotificationTemplate`,
  `BroadcastCampaign`, and `BroadcastDelivery`.
- Added Seller/Admin APIs for templates, campaign drafts, preview estimates,
  test sends, schedule/start, pause/cancel, bounded process-batch delivery, and
  delivery reports.
- Added Seller Panel Customer Notifications campaign, template, preview/test,
  detail, delivery report, and recipient registry views.
- Batch sending uses `TELEGRAM_CUSTOMER_BOT_TOKEN` only and stores sanitized
  delivery results. Bot 2 seller tooling remains separate.
- MVP supports safe audience filters for all eligible customers, purchasers,
  purchased product/category, and promo-code users. Recipient exports,
  arbitrary database interpolation, non-plain parse modes, and a dedicated
  background worker remain out of scope.

---

# Development Rules

- SQLAlchemy models + Alembic migrations are the source of truth for DB schema.
- No Prisma in Python backend.
- No business logic in FastAPI routers.
- Services own business rules.
- Repositories own database queries.
- Pydantic schemas own input/output validation.
- All order creation must be transaction-safe.
- All orders must persist in PostgreSQL before notifications.
- Telegram must not be a data source.
- File storage must remain replaceable.
- API contract must be exposed through OpenAPI.
- Frontend must not depend on backend internals.

---

# Final Architecture Flow

```text
Mini App / Seller Panel
        ↓
   FastAPI Backend API
        ↓
 SQLAlchemy ORM + Alembic
        ↓
   PostgreSQL Database
        ↓
 Redis / Storage / Telegram Bot API
```

---

# Outcome

После завершения sprint plan получится:

- полноценный Telegram-based marketplace;
- Python/FastAPI modular monolith backend;
- PostgreSQL-first commerce core;
- Seller-controlled ecosystem;
- OpenAPI contract для frontend;
- архитектура, готовая к миграции storage в S3/R2 и постепенному выделению сервисов.
