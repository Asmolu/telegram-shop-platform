# SRS — Telegram Shop Platform

## 1. Общая информация

Telegram Shop Platform — это e-commerce система, построенная вокруг Telegram Mini App и Seller Panel.

Система состоит из трёх основных частей:

- Telegram Mini App — клиент для покупателей;
- Seller Panel — web-панель продавца/администратора;
- Backend API — Python + FastAPI + SQLAlchemy + Alembic.

Система проектируется как **модульный монолит**, который можно развивать вертикальными срезами и позже частично выделять в отдельные сервисы.

---

## 2. Цель системы

Обеспечить полный цикл продаж:

- просмотр каталога товаров;
- поиск и фильтрация товаров;
- просмотр карточки товара;
- добавление товара в корзину;
- применение промокода;
- оформление заказа;
- оплата в будущем;
- управление товарами продавцом;
- обработка заказов;
- управление баннерами и промокодами;
- модерация отзывов;
- аналитика продаж и пользовательских действий.

---

## 3. Архитектура системы

### 3.1 Общая схема

```text
Telegram Mini App / Seller Panel
              ↓
        FastAPI Backend API
              ↓
     SQLAlchemy ORM + Alembic
              ↓
           PostgreSQL
```

Дополнительные компоненты:

- Redis — кэш, очереди, фоновые задачи;
- Local File Storage `/uploads` — MVP-хранилище файлов;
- Telegram Bot API — уведомления и Telegram-интеграция;
- OpenAPI — контракт между backend и frontend.

---

## 4. Технологический стек

### Backend

- Python 3.12+
- FastAPI
- Uvicorn
- Pydantic / Pydantic Settings
- SQLAlchemy 2.0 async ORM
- Alembic migrations
- PostgreSQL
- Redis
- Pytest

### Frontend

- React
- Vite
- TypeScript
- Telegram Mini Apps SDK / Telegram WebApp API

### Infrastructure

- Docker
- Docker Compose
- Local uploads storage
- PostgreSQL volume
- Redis container

---

## 5. Backend modules

Backend сохраняет feature-based структуру. Каждый модуль должен содержать собственные routers, schemas, services и database-access code.

Основные модули:

- `auth`
- `users`
- `products`
- `categories`
- `tags`
- `banners`
- `promo_codes`
- `cart`
- `orders`
- `reviews`
- `favorites`
- `notifications`
- `uploads`
- `telegram`
- `statistics`
- `events`
- `jobs`

---

## 6. Клиентские приложения

### 6.1 Telegram Mini App

Функции:

- просмотр каталога;
- поиск товаров;
- фильтрация;
- карточка товара;
- корзина;
- оформление заказа;
- промокоды;
- избранное;
- отзывы;
- профиль пользователя;
- история заказов.

Telegram Mini App не должен содержать критическую бизнес-логику. Он только показывает UI и вызывает Backend API.

---

### 6.2 Seller Panel

Функции:

- управление товарами;
- создание/редактирование товаров;
- управление вариантами и остатками;
- управление баннерами;
- управление промокодами;
- обработка заказов;
- изменение статусов заказов;
- модерация отзывов;
- аналитика.

Seller Panel работает через тот же Backend API, что и Mini App, но использует seller/admin права.

---

## 7. Доменные сущности

Сущности реализуются как SQLAlchemy models. Схема БД управляется Alembic migrations.

---

### User

Пользователь системы: покупатель, продавец или администратор.

Используется для:

- авторизации через Telegram;
- хранения Telegram profile data;
- хранения роли;
- заказов;
- отзывов;
- избранного;
- уведомлений;
- корзины.

Минимальные поля:

- `id`
- `telegram_id`
- `username`
- `first_name`
- `last_name`
- `phone`
- `role`
- `is_active`
- `created_at`
- `updated_at`

---

### Product

Основной товар каталога.

Содержит:

- название;
- slug;
- описание;
- базовую цену;
- статус;
- категорию;
- изображения;
- варианты товара;
- теги.

Статусы:

- DRAFT;
- ACTIVE;
- OUT_OF_STOCK;
- ARCHIVED.

---

### ProductVariant

Вариант товара: размер, SKU, остатки.

Пример:

- Hoodie / S / stock 4;
- Hoodie / M / stock 12;
- Hoodie / L / stock 0.

Используется для:

- size-based stock management;
- проверки доступности товара;
- списания остатков при checkout.

---

### ProductImage

Изображение товара.

Файл хранится в local storage:

```text
backend/uploads/products/
```

В БД хранится только путь к файлу, позиция и флаг главного изображения.

---

### Category

Категория товаров.

Примеры:

- Hoodies;
- T-Shirts;
- Jeans.

Может использоваться для фильтрации каталога и баннерных ссылок.

---

### Tag

Дополнительная метка товара.

Примеры:

- oversize;
- premium;
- streetwear;
- new;
- sale.

Product ↔ Tag — many-to-many relation.

---

### Banner

Рекламный баннер в приложении.

Может вести на:

- товар;
- категорию;
- промо-акцию;
- внешний URL.

Используется на главной странице Mini App и в Seller Panel.

---

### PromoCode

Промокод.

Поддерживает:

- процентную скидку;
- фиксированную скидку;
- лимит использований;
- период активности;
- активацию/деактивацию.

---

### CouponUsage

История использования промокода.

Используется для:

- ограничения повторного применения;
- аналитики;
- антифрода;
- связи промокода с заказом.

---

### Cart

Корзина пользователя.

Один пользователь имеет одну активную корзину.

---

### CartItem

Элемент корзины.

Содержит:

- product;
- variant;
- quantity;
- created_at;
- updated_at.

Перед checkout cart item должен проверяться на актуальный статус товара и остатки.

---

### Order

Заказ пользователя.

Содержит:

- номер заказа;
- пользователя;
- статус;
- subtotal;
- discount;
- total;
- контактные данные;
- адрес/комментарий;
- timestamps.

Order создаётся внутри DB transaction.

---

### OrderItem

Неизменяемый снимок товара в заказе.

Содержит:

- product id;
- variant id;
- название товара на момент покупки;
- размер/вариант на момент покупки;
- цену на момент покупки;
- количество;
- итоговую цену строки.

OrderItem не должен зависеть от будущих изменений Product.

---

### Review

Отзыв пользователя.

Правила:

- отзыв можно оставить только после покупки;
- отзыв создаётся со статусом PENDING;
- seller/admin модерирует отзыв;
- публично видны только APPROVED отзывы.

---

### Favorite

Избранный товар пользователя.

Используется для wishlist/favorites UI.

---

### Notification

Уведомление системы.

Типы:

- заказ создан;
- заказ принят в обработку;
- заказ отправлен;
- заказ доставлен;
- промокод применён;
- системное уведомление.

Может использоваться для Telegram Bot API и внутреннего notification center.

---

### AuditLog

Журнал действий продавцов и администраторов.

Фиксирует:

- кто выполнил действие;
- тип действия;
- сущность;
- старое значение;
- новое значение;
- timestamp.

Критические seller/admin действия должны логироваться.

---

### AnalyticsEvent

Событие поведения пользователя.

Примеры:

- product.viewed;
- cart.item_added;
- checkout.started;
- order.created;
- promo.used.

Используется для базовой аналитики и будущих отчётов.

---

## 8. Enum система

### UserRole

- USER
- SELLER
- ADMIN

---

### ProductStatus

- DRAFT
- ACTIVE
- OUT_OF_STOCK
- ARCHIVED

---

### OrderStatus

- NEW
- PROCESSING
- SHIPPED
- DELIVERED
- CANCELLED

---

### ReviewStatus

- PENDING
- APPROVED
- REJECTED

---

### DiscountType

- PERCENT
- FIXED

---

## 9. Хранилище файлов

### Текущее решение MVP

Локальное хранение:

```text
backend/uploads/
```

Структура:

```text
uploads/
├── products/
├── banners/
├── reviews/
└── temp/
```

### Правила

- файлы не хранятся в PostgreSQL;
- в БД хранится только относительный path;
- upload service должен скрывать конкретный storage backend;
- миграция в S3/R2 не должна требовать изменения бизнес-логики.

---

## 10. Основные бизнес-процессы

### 10.1 Покупка товара

1. Пользователь открывает Mini App.
2. Backend валидирует Telegram auth.
3. Пользователь выбирает товар.
4. Пользователь выбирает variant/size.
5. Пользователь добавляет товар в корзину.
6. Пользователь применяет промокод опционально.
7. Пользователь оформляет заказ.
8. Backend в transaction:
   - проверяет остатки;
   - создаёт Order;
   - создаёт OrderItems;
   - списывает stock;
   - фиксирует CouponUsage при наличии промокода;
   - очищает корзину.
9. После успешного commit создаётся notification event.
10. Seller получает Telegram notification.

---

### 10.2 Управление товаром seller/admin

1. Seller/Admin создаёт товар.
2. Добавляет описание, цену, категорию и теги.
3. Загружает изображения.
4. Создаёт ProductVariant с размерами и остатками.
5. Публикует товар через статус ACTIVE.
6. Действие фиксируется в AuditLog.

---

### 10.3 Отзывы

1. Пользователь покупает товар.
2. После заказа может оставить отзыв.
3. Backend проверяет факт покупки.
4. Отзыв получает статус PENDING.
5. Seller/Admin модерирует отзыв.
6. APPROVED отзыв отображается публично.

---

### 10.4 Промокоды

1. Пользователь вводит код.
2. Backend проверяет:
   - существование кода;
   - активность;
   - срок действия;
   - общий лимит;
   - пользовательский лимит;
   - применимость к текущей корзине.
3. Backend рассчитывает скидку.
4. При checkout создаётся CouponUsage.

---

## 11. API contract

Backend должен отдавать OpenAPI schema.

Frontend должен работать с backend через:

- typed API client;
- generated OpenAPI client;
- либо общий hand-written wrapper в `shared/api`.

Frontend не должен импортировать backend-код напрямую.

---

## 12. Нефункциональные требования

### Производительность

MVP-цель:

- до 10k MAU;
- до 1000 concurrent users как целевой ориентир, не как гарантия без нагрузочного тестирования;
- обязательная pagination для списков;
- индексы на frequently queried fields.

---

### Надёжность

- PostgreSQL — источник истины;
- Redis используется как вспомогательный слой;
- Telegram не является источником данных;
- order creation должна быть transaction-safe;
- уведомления отправляются после сохранения заказа;
- миграции БД выполняются через Alembic.

---

### Масштабируемость

Система должна позволять:

- миграцию файлов в S3/R2 без изменения доменной модели;
- выделение `orders`, `products`, `notifications` в отдельные сервисы в будущем;
- добавление очередей и фоновых задач;
- добавление платёжной системы;
- расширение аналитики.

---

## 13. Безопасность

- Telegram initData validation;
- JWT для API-запросов;
- RBAC для USER / SELLER / ADMIN;
- Seller/Admin separation;
- Audit logging критических действий;
- rate limiting для auth и публичных endpoints;
- file upload validation;
- CORS allowlist;
- отсутствие секретов в git.

---

## 14. Событийная модель

События:

- `order.created`
- `order.status_changed`
- `order.shipped`
- `product.updated`
- `promo.used`
- `review.created`

Используется для:

- уведомлений;
- аналитики;
- audit logging;
- фоновых задач;
- будущей интеграции с внешними сервисами.

---

## 15. Будущие улучшения

- Cloud storage: S3 / Cloudflare R2;
- online payments;
- recommendation system;
- full analytics dashboard;
- advanced inventory reservation;
- email/SMS notifications;
- background workers;
- microservices split optional.

---

## 16. Итог

Telegram Shop Platform — это модульный монолит на Python/FastAPI, PostgreSQL, SQLAlchemy и Alembic.

Архитектура сохраняет исходную доменную модель e-commerce проекта, но убирает зависимость от NestJS/Prisma. Backend становится Python-first, а frontend продолжает работать как React/Vite TypeScript UI через OpenAPI-контракт.
---

## 17. Sprint 14 production hardening baseline

MVP production/staging readiness requires:

- Redis-backed caching for hot public catalog endpoints with graceful PostgreSQL fallback.
- Configurable rate limiting for global API traffic and stricter sensitive write endpoints.
- Structured request logging with request IDs, status, path, method, and duration.
- Error-monitoring configuration placeholders without requiring a third-party account for local development.
- Production Docker Compose profile with persistent PostgreSQL, Redis, and uploads volumes.
- Documented PostgreSQL and uploads backup/restore workflow.
- Production settings that reject default JWT secrets and wildcard CORS origins.
- Alembic migrations for new schema/index changes only; old migrations remain immutable.

---

## 18. Seller Portal email auth and Bot 2 verification

Seller Portal supports email/password login for SELLER/ADMIN users through the
FastAPI backend. Public registration can create only SELLER accounts and must be
verified through Bot 2 before JWT login is allowed.

Registration flow:

1. Seller submits email, password, and Telegram username in Seller Panel.
2. Backend stores a pending registration with hashed password, hashed start
   token, and no trusted Telegram identity yet.
3. Seller opens Bot 2 with `/start seller_<token>`.
4. Backend links the Telegram user/chat identity from Bot 2 and validates the
   username when available.
5. Bot 2 sends an expiring verification code.
6. Seller confirms the code in Seller Panel, backend creates or upgrades a
   SELLER user, stores `SellerCredential`, and returns a JWT.

Bot 2 is configured only in backend environment variables. The frontend must
never receive bot tokens. Until webhook/polling is wired, the backend exposes a
manual HTTP callback boundary for Bot 2 start-link handling.

Seller Bot management is restricted to SELLER/ADMIN users. MVP broadcast sends
only to the configured seller notification chat and records audit log entries;
it is not an all-customer broadcast without stored recipient chat IDs and user
consent.
