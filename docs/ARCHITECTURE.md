# Архитектура StyleXac

**Срез:** commit `325e3af`, Alembic `20260713_0056`, 13 июля 2026 года. Этот стабильный путь содержит краткий обзор; канонический документ — [Engineering Architecture](engineering/ARCHITECTURE.md).

Система состоит из FastAPI backend, PostgreSQL 16, Redis 7, React Mini App, React Seller Panel и двух Telegram-ботов. PostgreSQL — source of truth; Redis — временное состояние/cache/rate limit. Bot 1 обслуживает покупателей, Bot 2 — seller/admin/auth. Frontend не содержит доверенной auth/business logic.

Backend организован как `router → service → repository`: router отвечает за HTTP, service — за бизнес-правила и транзакции, repository — за async SQLAlchemy queries. Checkout атомарно блокирует и списывает stock, а `OrderItem` хранит immutable snapshot. События уведомлений создаются после persistence через outbox.

Подробнее: [System Context](engineering/SYSTEM_CONTEXT.md), [Components](engineering/COMPONENTS.md), [Domain Model](engineering/DOMAIN_MODEL.md), [Authentication](engineering/AUTHENTICATION_AND_RBAC.md), [Outbox](engineering/OUTBOX_ARCHITECTURE.md). Production topology и ограничения описаны в [Production State](PRODUCTION_STATE.md).
