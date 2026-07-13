# Операции StyleXac

**Production snapshot:** commit `325e3af`, Alembic `20260713_0056`, 13 июля 2026 года. Домены: `stylexac.ru`, `mini.stylexac.ru`, `api.stylexac.ru`, `seller.stylexac.ru`. Host path: `/opt/telegram-shop`.

Канонический day-2 документ — [Operations Runbook](operations/OPERATIONS_RUNBOOK.md), deployment — [Production Deployment](PRODUCTION_DEPLOYMENT.md). Ежедневно контролируются health, containers, errors, workers/outbox, PostgreSQL/Redis, disk/uploads и backup. Campaign/channel actions требуют отдельного подтверждения, Bot 1/Bot 2 не смешиваются.

Backup запускается через `telegram-shop-backup.service`, а не прямым непроверенным dump: service должен создать копию, проверить восстановление и применить retention. Repository unit template содержит известный устаревший path `/opt/TelegramShopPlatform`; установленный unit обязан использовать `/opt/telegram-shop`.

Инциденты: [Incident Response](operations/INCIDENT_RESPONSE.md), [Monitoring](operations/MONITORING_AND_ALERTING.md), [Disaster Recovery](operations/DISASTER_RECOVERY.md), [Rollback](operations/ROLLBACK.md), [Maintenance](operations/MAINTENANCE.md).
