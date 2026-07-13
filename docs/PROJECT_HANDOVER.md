# Передача проекта StyleXac / ICON STORE

**Срез:** commit `325e3af2a79dd9d4af92050e272169828d0edfbf`, Alembic `20260713_0056`, 13 июля 2026 года. **Аудитория:** новый владелец продукта, developer, operator, support lead и seller success. Все production-секреты и персональные данные намеренно исключены.

## 1. Что передается

TelegramShopPlatform — monorepo commerce-продукта ICON STORE под брендом StyleXac:

- `backend/`: Python 3.12+, FastAPI, async SQLAlchemy, Alembic, PostgreSQL 16, Redis 7;
- `mini-app/`: mobile-first React/Vite/TypeScript Telegram Mini App;
- `seller-panel/`: desktop-first React/Vite/TypeScript Seller Panel;
- `bots/`/backend bot modules: Bot 1 для customer lifecycle, Bot 2 для seller/admin/auth;
- local uploads с путями/URL в БД и будущей S3/R2-совместимостью;
- Docker Compose, Caddy, backup scripts, tests и полный documentation pack.

Главный домен — `https://stylexac.ru`, прямые точки: `mini.stylexac.ru`, `api.stylexac.ru`, `seller.stylexac.ru`. Production host — Aeza Frankfurt, alias `tsplatform-frankfurt`, path `/opt/telegram-shop`.

## 2. Подтвержденное состояние

Релиз 13 июля 2026 года подтвержден для commit `325e3af` и migration head `0056`: backend healthy, main/Mini/Seller/API health отвечали HTTP 200, PostgreSQL и Redis продолжали работу, migrations `0055` и `0056` применены. Перед deploy создан fresh local backup, restore verification прошла; remote upload конкретного manual backup был skipped. Исторического bulk backfill in-app notifications не выполнялось. Это снимок релиза, не SLA и не гарантия текущей доступности.

## 3. Бизнес-контур

Canonical rules: [Business Rules](product/BUSINESS_RULES.md), [Delivery](product/DELIVERY.md), [Order Lifecycle](product/ORDER_LIFECYCLE.md), [Payment Lifecycle](product/PAYMENT_LIFECYCLE.md), [Returns and Refunds](product/RETURNS_AND_REFUNDS.md), [Notifications](product/NOTIFICATIONS.md).

Покупатель авторизуется через проверяемый backend Telegram `initData`, изучает каталог/search/Looks, выбирает варианты, оформляет transactional checkout, получает `ORD-xxxxxx`, выполняет ручную СБП и следит за заказом/уведомлениями. После покупки доступны модерируемый review и, по текущей механике, return в течение 24 часов после delivery.

Seller управляет catalog/listing/stock, заказом, payment confirmation, fulfillment, returns/refunds, reviews, campaigns и channel entry. Admin имеет платформенные полномочия. Критические операции должны попадать в `AuditLog`; поведенческие события — в `AnalyticsEvent` где предусмотрено.

Ключевые нюансы:

- `is_listed=false` скрывает ACTIVE товар из discovery, но detail по прямому id/slug остается доступным;
- Look ACTIVE требует хотя бы один `is_default_selected`, однако текущая сборка/API/UI фактически выбирает все компоненты;
- coupon уменьшает goods subtotal, delivery добавляется после;
- pickup доменно не требует адрес, но текущая checkout schema требует непустой адрес для любого метода;
- order status технически допускает нелинейные переходы/re-entry;
- customer cancel endpoint не подтвержден;
- manual payment: `PENDING → SUBMITTED → APPROVED | REJECTED`, active может стать `EXPIRED`; approve ведет заказ в processing, reject/expire — в cancelled с release stock;
- refund ручной, delivery автоматически исключена, restock delta-safe.

Подробности: [Product Overview](product/PRODUCT_OVERVIEW.md), [Business Rules](product/BUSINESS_RULES.md), [Known Limitations](KNOWN_LIMITATIONS.md).

## 4. Архитектурные инварианты

PostgreSQL — source of truth; Redis — cache/rate limit/temporary state. Router только разбирает HTTP и вызывает service; service содержит правила/transactions; repository содержит SQLAlchemy queries. Checkout блокирует variants и атомарно списывает stock; `OrderItem` — immutable snapshot. Уведомления формируются только после persistence через outbox. Raw Telegram `initData` не хранится и не логируется.

Модели пока находятся в `backend/app/db/models.py`, feature modules — в `backend/app/modules/<feature>/`. Схемное изменение всегда требует Alembic. Backend остается Python; NestJS/Prisma/Node backend запрещены. Frontend API base задается env, production URL не hardcode.

## 5. Операции

Deployment выполняется только с утвержденным change по [Production Deployment](PRODUCTION_DEPLOYMENT.md). Exact compose prefix:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml
```

Перед migrations обязательны clean worktree, compose config, backup service и restore evidence. Установленный systemd unit необходимо проверить: repository template содержит устаревший `/opt/TelegramShopPlatform`, а текущий путь `/opt/telegram-shop`. Backup intent: ежедневно 04:00 Europe/Moscow, local retention 3 дня/max 20, remote 14 дней/max 2, remote cadence 7; lock/state и restore verification обязательны.

Операционные документы: [Runbook](operations/OPERATIONS_RUNBOOK.md), [Backup](operations/BACKUP_AND_RESTORE.md), [Monitoring](operations/MONITORING_AND_ALERTING.md), [Incident Response](operations/INCIDENT_RESPONSE.md), [DR](operations/DISASTER_RECOVERY.md), [Rollback](operations/ROLLBACK.md).

## 6. Разработка и релиз

Начать с [Development](engineering/DEVELOPMENT.md), [Configuration](engineering/CONFIGURATION.md), [Testing](engineering/TESTING.md) и repository `AGENTS.md`. UI-изменения требуют чтения `UI_DESIGN_SPEC.README.md`. Не читать и не менять реальные env без необходимости и разрешения.

Текущий release evidence, предоставленный для этого среза:

- backend strict: 1098 passed, 3 skipped (Windows `fcntl`);
- focused PostgreSQL outbox/in-app: 19;
- migration tests: 48; focused backend: 416;
- Mini App: 258, focused notifications: 21;
- Seller Panel: 75;
- frontend builds, Mini production Docker build и Alembic check прошли.

Эти числа — snapshot, не автоматическая гарантия следующего commit. Перед завершением изменений выполняются проверки из `AGENTS.md` для затронутой области и `git diff --check`.

## 7. Security, privacy и legal gates

Код содержит Telegram HMAC/freshness, RBAC/scope, rate limiting, audit, транзакции, outbox и backup, но independent pentest и production IAM review не подтверждены этой работой. До продаж нужны security sign-off, legal texts, personal-data mapping, retention, processors, СБП/ККТ решение и review 24-часовой return policy.

См. [Security Checklist](security/SECURITY_CHECKLIST.md), [Threat Model](security/THREAT_MODEL.md), [Legal Checklist](legal/LEGAL_READINESS_CHECKLIST.md) и [Returns Gap](legal/RETURNS_POLICY_GAP_ANALYSIS.md).

## 8. Первые действия нового владельца

1. Сверить commit/head, owners, доступы и конфиденциальные контакты вне Git.
2. Прочитать [Master Document](PROJECT_MASTER_DOCUMENT.md) и [Documentation Index](README.md).
3. Провести walkthrough product → seller → support → operations на staging.
4. Проверить installed systemd unit, alerts, backup restore drill и incident contacts.
5. Закрыть legal/security checklist либо письменно принять риски.
6. Зафиксировать ближайший release scope, UAT и rollback owner.
7. Не объявлять partial/unknown функции production-ready; сверяться с [Feature Evidence Matrix](sales/FEATURE_EVIDENCE_MATRIX.md).

## 9. Нерешенные приоритеты

P0/P1 до широкого коммерческого запуска: independent security assessment, legal readiness, устранение/формализация status-transition и pickup-address разрывов, policy по upload malware/retention, проверка production monitoring и unit path. Далее — Look defaults, customer cancellation, automated payments/reconciliation, integrations и observability maturity.

## 10. Граница передачи

Документация передает знания и воспроизводимые процедуры, но не credentials, договоры, живые метрики или полномочия на production. Доступы передаются по отдельному защищенному процессу с MFA/least privilege и подтверждением владельцев. Любое расхождение живой среды и этого среза регистрируется в [Changelog](CHANGELOG.md) и обновляет [Production State](PRODUCTION_STATE.md).
