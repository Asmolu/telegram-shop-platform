# TelegramShopPlatform / ICON STORE

TelegramShopPlatform — репозиторий продукта **ICON STORE** (StyleXac): Telegram-commerce
платформы с клиентским Mini App, desktop Seller Panel, FastAPI API и двумя Telegram-ботами
с раздельной ответственностью.

## Production state

Подтвержденный снимок на **2026-07-13**:

| Параметр | Значение |
| --- | --- |
| Ветка / commit | `main` / `325e3af2a79dd9d4af92050e272169828d0edfbf` |
| Alembic head | `20260713_0056` |
| Main / Mini App entry | `https://stylexac.ru` |
| Mini App | `https://mini.stylexac.ru` |
| API | `https://api.stylexac.ru` |
| Seller Panel | `https://seller.stylexac.ru` |

Backend был healthy, а четыре HTTP-проверки вернули 200 при приемке релиза. Это снимок,
а не гарантия постоянной доступности. Домены семейства `tsplatform.ru` deprecated.

Источник: `docker-compose.prod.yml`, `deploy/caddy/Caddyfile.frankfurt.example`,
`backend/alembic/versions/20260713_0056_add_customer_in_app_notifications.py`.

## Пользователи и функции

- **Customer**: catalog, categories, search, Looks, favorites, cart, promo, checkout,
  manual payment, orders, returns, reviews и notifications.
- **SELLER / ADMIN**: catalog и stock, orders/payments, returns/refunds, moderation,
  Looks, banners, campaigns, channel entry, settings, blocks, analytics и audit.
- **Operator**: Compose deployment, Alembic, backup/restore verification и runbooks.
- **Bot 1**: покупательские `/start`, `/stop`, service/marketing notifications,
  channel entry publish/pin.
- **Bot 2**: seller/admin/auth, payment и return callbacks.

Платеж подтверждается продавцом вручную. Payment provider, acquiring, online cash register
и automatic fiscal receipts не реализованы. 24-часовое окно возврата — программное правило,
которое требует отдельной юридической проверки.

Канонические доказательства:
[Feature Catalog](docs/product/FEATURE_CATALOG.md) и
[Feature Evidence Matrix](docs/sales/FEATURE_EVIDENCE_MATRIX.md).

## Архитектура и стек

| Слой | Технологии |
| --- | --- |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2 async, Alembic, Uvicorn |
| Data | PostgreSQL 16 (source of truth), Redis 7 (cache/rate limit/temporary state) |
| Frontend | React, TypeScript, Vite |
| Runtime | Docker Compose, host reverse proxy, systemd backup timer |
| Files | local uploads volume; PostgreSQL хранит только paths/URLs |
| Quality | Pytest, Ruff, Vitest, TypeScript checks, bundle verification |

Routers разбирают HTTP, services владеют бизнес-правилами и транзакциями, repositories —
SQLAlchemy queries. Checkout блокирует варианты, атомарно проверяет/уменьшает stock и создает
immutable OrderItem snapshots. Orders/payments используют PostgreSQL transactional outbox.

Источник: `backend/app/modules/`, `backend/app/db/models.py`,
`backend/app/modules/orders/service.py`, `backend/app/modules/outbox/`.

## Репозиторий

```text
backend/       API, models, migrations, workers, backup scripts, tests
mini-app/      mobile-first Telegram Mini App
seller-panel/  desktop-first Seller Panel
docs/          product, sales, engineering, operations, security, legal
deploy/        reverse-proxy example
scripts/       systemd templates
```

## Локальный старт

Нужны Docker Engine/Desktop с Compose. Для нативного запуска: Python 3.12+ и Node.js/npm.
Точная поддерживаемая Node.js LTS версия пока не утверждена.

```powershell
Copy-Item backend/.env.example backend/.env
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

`backend/.env` — local development/checks. `backend/.env.production` — VDS/server
operations и production-domain checks. Реальные значения secrets нельзя копировать в docs.

Подробно: [Local Development](docs/LOCAL_DEVELOPMENT.md),
[Configuration](docs/engineering/CONFIGURATION.md).

## Проверки

```powershell
Set-Location backend
python -m compileall app tests
ruff check .
pytest
pytest -W error

Set-Location ../mini-app
npm test -- --run
npm run build
npm run verify:bundle

Set-Location ../seller-panel
npm run lint
npm run typecheck
npm test -- --run
npm run build

Set-Location ..
git diff --check
```

Снимок release checks: [Testing](docs/TESTING.md).

## Production кратко

Production path: `/opt/telegram-shop`. Канонический вызов:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml <command>
```

Перед migration обязателен проверенный backup через `telegram-shop-backup.service`.
Команды выполняются короткими фазами с проверкой commit, Alembic, compose config, health
и logs. Полная инструкция: [Production Deployment](docs/PRODUCTION_DEPLOYMENT.md).
Любое production-действие требует отдельного разрешения и доступа оператора.

## Документация

- [Навигатор и confidentiality](docs/README.md)
- [Master document](docs/PROJECT_MASTER_DOCUMENT.md)
- [Project handover](docs/PROJECT_HANDOVER.md)
- [Production state](docs/PRODUCTION_STATE.md)
- [Product](docs/product/PRODUCT_OVERVIEW.md)
- [Sales](docs/sales/PRODUCT_ONE_PAGER.md)
- [Engineering](docs/engineering/ARCHITECTURE.md)
- [Operations](docs/operations/OPERATIONS_RUNBOOK.md)
- [Security](docs/security/SECURITY_OVERVIEW.md)
- [Legal readiness](docs/legal/LEGAL_READINESS_CHECKLIST.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Contributing](docs/engineering/CONTRIBUTING.md)

## Security и commercial readiness

Не коммитьте `.env`, `.env.production`, credentials, tokens, private chat identifiers,
database dumps, uploads или персональные данные. Telegram `initData` валидируется backend;
raw `initData` не логируется и не сохраняется.

Продукт deployed и пригоден для контролируемой демонстрации, но pricing, SLA, RPO/RTO и
legal documents не утверждены; payment automation отсутствует; offsite backup не гарантирован
каждым запуском; topology single-server. Допустимые sales claims и blockers:
[Sales Readiness](docs/SALES_READINESS.md).
