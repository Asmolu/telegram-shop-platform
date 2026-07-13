# Навигация по документации StyleXac

**Срез каталога:** commit `325e3af`, 13 июля 2026 года. Документы описывают подтвержденное состояние репозитория и указанный production snapshot; живую среду нужно проверять отдельно.

Уровни: **Public** — допустимо адаптировать для внешней аудитории; **Seller-facing** — для подключенного продавца; **Internal** — команда/партнер под NDA; **Restricted** — только уполномоченные operations/security, без секретов даже внутри файла. Авторитетный вход — [Project Master Document](PROJECT_MASTER_DOCUMENT.md), состояние — [Production State](PRODUCTION_STATE.md), ограничения — [Known Limitations](KNOWN_LIMITATIONS.md).

## Customer-facing и публичные документы

| Документ | Аудитория | Назначение | Класс | Источник истины / дата |
| --- | --- | --- | --- | --- |
| [Product Overview](product/PRODUCT_OVERVIEW.md) | Покупатель/партнер | Обзор продукта | Public | Код + snapshot / 2026-07-13 |
| [Feature Catalog](product/FEATURE_CATALOG.md) | Sales/buyer | Полный каталог функций и статусов | Public | Код/tests / 2026-07-13 |
| [User Flows](product/USER_FLOWS.md) | Product/demo | Сквозные сценарии | Public | UI/API / 2026-07-13 |
| [Glossary](GLOSSARY.md) | Все | Единые термины | Public | Domain/code / 2026-07-13 |
| [Product One-pager](sales/PRODUCT_ONE_PAGER.md) | Prospect | Краткое позиционирование | Public | Evidence matrix / 2026-07-13 |
| [Commercial Scope](sales/COMMERCIAL_SCOPE.md) | Buyer/sales | In/out of scope | Public | Repository scope / 2026-07-13 |
| [Customer Support FAQ](sales/CUSTOMER_SUPPORT_FAQ.md) | Покупатель/support | Проверенные ответы | Public | Business rules / 2026-07-13 |

## Внутренний коммерческий пакет

| Документ | Аудитория | Назначение | Класс | Источник истины / дата |
| --- | --- | --- | --- | --- |
| [Sales Readiness](SALES_READINESS.md) | Owner/sales | Gate коммерческого запуска | Internal | Audit / 2026-07-13 |
| [Sales Playbook](sales/SALES_PLAYBOOK.md) | Sales | Discovery и продажа | Internal | Product pack / 2026-07-13 |
| [Demo Script](sales/DEMO_SCRIPT.md) | Presales | Безопасная демонстрация | Internal | UI/API / 2026-07-13 |
| [Feature Evidence Matrix](sales/FEATURE_EVIDENCE_MATRIX.md) | Buyer/due diligence | Функция → доказательство → gap | Internal | Code/tests / 2026-07-13 |
| [Objection Handling](sales/OBJECTION_HANDLING.md) | Sales | Честные ответы на возражения | Internal | Known limitations / 2026-07-13 |
| [Due Diligence Package](sales/DUE_DILIGENCE_PACKAGE.md) | Technical buyer | Индекс evidences | Internal | Documentation pack / 2026-07-13 |

## Продавец и поддержка

| Документ | Аудитория | Назначение | Класс | Источник истины / дата |
| --- | --- | --- | --- | --- |
| [Seller Onboarding](sales/SELLER_ONBOARDING.md) | Seller success | Подключение магазина | Seller-facing | Product/ops / 2026-07-13 |
| [Seller Acceptance Checklist](sales/SELLER_ACCEPTANCE_CHECKLIST.md) | Seller/QA | UAT и приемка | Seller-facing | Flows/tests / 2026-07-13 |
| [Support Runbook](operations/SUPPORT_RUNBOOK.md) | Support | Триаж и эскалация | Seller-facing | Domain/ops / 2026-07-13 |
| [Roles and Permissions](product/ROLES_AND_PERMISSIONS.md) | Seller/admin | Роли и границы | Seller-facing | Auth/RBAC code / 2026-07-13 |
| [Business Rules](product/BUSINESS_RULES.md) | Product/support | Авторитетные правила | Seller-facing | Services/schemas / 2026-07-13 |
| [Order Lifecycle](product/ORDER_LIFECYCLE.md) | Seller/support | Заказ и stock | Seller-facing | Orders code / 2026-07-13 |
| [Payment Lifecycle](product/PAYMENT_LIFECYCLE.md) | Seller/support | Ручная СБП | Seller-facing | Payments code / 2026-07-13 |
| [Returns and Refunds](product/RETURNS_AND_REFUNDS.md) | Seller/support | Return/refund flow | Seller-facing | Returns code / 2026-07-13 |
| [Delivery](product/DELIVERY.md) | Seller/support | Методы, цены, gaps | Seller-facing | Checkout code / 2026-07-13 |
| [Looks](product/LOOKS.md) | Product/seller | Образы и выбор компонентов | Seller-facing | Looks code/UI / 2026-07-13 |
| [Search and Discovery](product/SEARCH_AND_DISCOVERY.md) | Product/seller | Видимость и поиск | Seller-facing | Products/search / 2026-07-13 |
| [Reviews and Favorites](product/REVIEWS_AND_FAVORITES.md) | Seller/support | Правила отзывов/избранного | Seller-facing | Modules/tests / 2026-07-13 |
| [Notifications](product/NOTIFICATIONS.md) | Seller/support | Каналы и eligibility | Seller-facing | Notifications code / 2026-07-13 |

## Engineering

| Документ | Аудитория | Назначение | Класс | Источник истины / дата |
| --- | --- | --- | --- | --- |
| [Engineering Architecture](engineering/ARCHITECTURE.md) | Developer/buyer | Каноническая архитектура | Internal | Code/compose / 2026-07-13 |
| [System Context](engineering/SYSTEM_CONTEXT.md) | Architect | Внешние границы | Internal | Integrations / 2026-07-13 |
| [Components](engineering/COMPONENTS.md) | Developer | Компоненты и ответственность | Internal | Source tree / 2026-07-13 |
| [Domain Model](engineering/DOMAIN_MODEL.md) | Developer/product | Доменные сущности | Internal | Models/services / 2026-07-13 |
| [Database Schema](engineering/DATABASE_SCHEMA.md) | Backend/DBA | Таблицы и миграции | Restricted | Models/Alembic / 2026-07-13 |
| [Backend Architecture](engineering/BACKEND_ARCHITECTURE.md) | Backend | Модульные правила | Internal | Backend code / 2026-07-13 |
| [Frontend Architecture](engineering/FRONTEND_ARCHITECTURE.md) | Frontend | Два React-приложения | Internal | Frontend code/spec / 2026-07-13 |
| [Authentication and RBAC](engineering/AUTHENTICATION_AND_RBAC.md) | Backend/security | Auth и authorization | Restricted | Auth code/tests / 2026-07-13 |
| [Telegram Integration](engineering/TELEGRAM_INTEGRATION.md) | Developer/operator | Bot 1/Bot 2/Mini App | Internal | Bot/auth modules / 2026-07-13 |
| [Outbox Architecture](engineering/OUTBOX_ARCHITECTURE.md) | Backend/operator | Durable delivery | Internal | Outbox code/tests / 2026-07-13 |
| [In-app Notifications](engineering/IN_APP_NOTIFICATIONS_ARCHITECTURE.md) | Backend/frontend | Durable notification model | Internal | Code/tests / 2026-07-13 |
| [API Reference](engineering/API_REFERENCE.md) | Developer/integrator | 193 OpenAPI operations | Internal | Local `app.openapi()` / 2026-07-13 |
| [Configuration](engineering/CONFIGURATION.md) | Developer/operator | Env catalog без значений | Restricted | Settings/examples/compose / 2026-07-13 |
| [Development](engineering/DEVELOPMENT.md) | Developer | Локальный старт | Internal | Repository / 2026-07-13 |
| [Testing](engineering/TESTING.md) | Developer/QA | Test strategy и snapshot | Internal | Tests/release evidence / 2026-07-13 |
| [Contributing](engineering/CONTRIBUTING.md) | Developer | Правила изменений | Internal | AGENTS/workflow / 2026-07-13 |
| [Release Process](engineering/RELEASE_PROCESS.md) | Release owner | Gates и evidence | Restricted | CI/ops / 2026-07-13 |

## Operations

| Документ | Аудитория | Назначение | Класс | Источник истины / дата |
| --- | --- | --- | --- | --- |
| [Production Deployment](PRODUCTION_DEPLOYMENT.md) | Operator | Авторитетный deploy runbook | Restricted | Compose/confirmed prod / 2026-07-13 |
| [Operations Runbook](operations/OPERATIONS_RUNBOOK.md) | Operator | Day-2 операции | Restricted | Scripts/compose / 2026-07-13 |
| [Backup and Restore](operations/BACKUP_AND_RESTORE.md) | Operator/DBA | Backup, retention, verify | Restricted | Scripts/systemd / 2026-07-13 |
| [Disaster Recovery](operations/DISASTER_RECOVERY.md) | Incident lead | Восстановление сервиса | Restricted | Backup/architecture / 2026-07-13 |
| [Monitoring and Alerting](operations/MONITORING_AND_ALERTING.md) | Operator | Signals и alerts | Restricted | Health/workers / 2026-07-13 |
| [Incident Response](operations/INCIDENT_RESPONSE.md) | Incident team | Командование инцидентом | Restricted | Ops policy / 2026-07-13 |
| [Rollback](operations/ROLLBACK.md) | Release/DBA | Safe rollback/forward fix | Restricted | Git/images/Alembic / 2026-07-13 |
| [Database Operations](operations/DATABASE_OPERATIONS.md) | DBA/backend | Alembic/PostgreSQL | Restricted | Models/migrations / 2026-07-13 |
| [Telegram Operations](operations/TELEGRAM_OPERATIONS.md) | Bot operator | Боты, channel, campaigns | Restricted | Telegram modules / 2026-07-13 |
| [Maintenance](operations/MAINTENANCE.md) | Operator | Регулярные работы | Restricted | Runbooks / 2026-07-13 |
| [Operations Deployment Index](operations/PRODUCTION_DEPLOYMENT.md) | Operator | Короткая навигация к runbook | Restricted | Canonical deploy doc / 2026-07-13 |

## Restricted security и privacy

| Документ | Аудитория | Назначение | Класс | Источник истины / дата |
| --- | --- | --- | --- | --- |
| [Security Overview](security/SECURITY_OVERVIEW.md) | Security/buyer | Контроли и границы | Internal | Code/config / 2026-07-13 |
| [Threat Model](security/THREAT_MODEL.md) | Security/engineering | Угрозы и mitigations | Restricted | Architecture/code / 2026-07-13 |
| [Data Classification](security/DATA_CLASSIFICATION.md) | Privacy/security | Классы данных | Restricted | Domain inventory / 2026-07-13 |
| [Privacy and Personal Data](security/PRIVACY_AND_PERSONAL_DATA.md) | Privacy/product | Принципы обработки | Internal | Data map / 2026-07-13 |
| [Secrets Management](security/SECRETS_MANAGEMENT.md) | Operator/developer | Жизненный цикл секретов | Restricted | Env/ops policy / 2026-07-13 |
| [Access Control](security/ACCESS_CONTROL.md) | Security/admin | App/infra доступы | Restricted | RBAC/ops / 2026-07-13 |
| [Security Checklist](security/SECURITY_CHECKLIST.md) | Launch owner | Security gates | Restricted | Threat model / 2026-07-13 |

## Legal readiness

| Документ | Аудитория | Назначение | Класс | Источник истины / дата |
| --- | --- | --- | --- | --- |
| [Legal Readiness Checklist](legal/LEGAL_READINESS_CHECKLIST.md) | Owner/legal | Legal gates | Internal | Product/data audit / 2026-07-13 |
| [Customer Documents Required](legal/CUSTOMER_DOCUMENTS_REQUIRED.md) | Legal/product | Требуемые тексты | Internal | Customer flows / 2026-07-13 |
| [Personal Data Processing Map](legal/PERSONAL_DATA_PROCESSING_MAP.md) | Privacy/legal | Карта процессов | Restricted | Models/flows / 2026-07-13 |
| [Returns Policy Gap](legal/RETURNS_POLICY_GAP_ANALYSIS.md) | Legal/product | Код против policy | Internal | Returns code / 2026-07-13 |

## Управление и совместимость

| Документ | Аудитория | Назначение | Класс | Источник истины / дата |
| --- | --- | --- | --- | --- |
| [Project Master Document](PROJECT_MASTER_DOCUMENT.md) | Owner/all leads | Авторитетное описание и карта истины | Internal | Full repository audit / 2026-07-13 |
| [Project Handover](PROJECT_HANDOVER.md) | New owner/operator | Автономная передача проекта | Restricted | Canonical pack / 2026-07-13 |
| [Production State](PRODUCTION_STATE.md) | Owner/operator | Подтвержденный release snapshot | Internal | Confirmed release record / 2026-07-13 |
| [Known Limitations](KNOWN_LIMITATIONS.md) | Owner/buyer | Реестр gaps и рисков | Internal | Code/docs audit / 2026-07-13 |
| [Documentation Audit](DOCUMENTATION_AUDIT.md) | Maintainer | Классификация старых файлов | Internal | Markdown inventory / 2026-07-13 |
| [Changelog](CHANGELOG.md) | Maintainer/release | История documentation pack | Internal | Git/migrations / 2026-07-13 |
| [Archive Policy](archive/README.md) | Maintainer | Правила архивации | Internal | Documentation policy / 2026-07-13 |
| [Architecture Compatibility](ARCHITECTURE.md) | Developer | Стабильный старый architecture path | Internal | Engineering architecture / 2026-07-13 |
| [Environment Compatibility](ENVIRONMENT.md) | Developer/operator | Стабильный env path | Restricted | Configuration / 2026-07-13 |
| [Local Development Compatibility](LOCAL_DEVELOPMENT.md) | Developer | Краткие локальные команды | Internal | Development guide / 2026-07-13 |
| [Testing Compatibility](TESTING.md) | Developer/QA | Release snapshot и ссылка на канон | Internal | Testing guide / 2026-07-13 |
| [Operations Compatibility](OPERATIONS.md) | Operator | Краткий day-2 вход | Restricted | Operations runbook / 2026-07-13 |
| [Backup Compatibility](BACKUP_AND_RESTORE.md) | Operator/DBA | Стабильный backup path | Restricted | Backup runbook / 2026-07-13 |
| [Backup Strategy Compatibility](BACKUP_STRATEGY.md) | Owner/operator | Policy summary | Restricted | Backup runbook / 2026-07-13 |
| [Customer Notifications Compatibility](CUSTOMER_NOTIFICATIONS_ARCHITECTURE.md) | Developer/support | Стабильный notification path | Internal | Notification canon / 2026-07-13 |
| [Security Review Compatibility](SECURITY_REVIEW.md) | Security/buyer | Текущий posture summary | Restricted | Security pack / 2026-07-13 |
| [Telegram Channel Entry Compatibility](TELEGRAM_CHANNEL_ENTRY.md) | Seller/operator | Focused channel flow | Seller-facing | Telegram modules / 2026-07-13 |
| [Frankfurt Readiness Compatibility](FRANKFURT_DEPLOYMENT_READINESS.md) | Release owner | Point-in-time readiness warning | Restricted | Production state / 2026-07-13 |
| [Analytics Telemetry](ANALYTICS_TELEMETRY.md) | Product/privacy | Event principles | Internal | Analytics code/data map / 2026-07-13 |
| [Codex Workflow](CODEX_WORKFLOW.md) | Coding agent | Agent workflow | Internal | `AGENTS.md` / 2026-07-13 |
| [GitHub Setup](GITHUB_SETUP.md) | Contributor | Repository workflow | Internal | Git policy / 2026-07-13 |

При изменении кода, инфраструктуры, env, доменов, bot responsibilities или бизнес-правил обновляйте канонический документ, совместимый старый путь и [Changelog](CHANGELOG.md) в том же PR.
