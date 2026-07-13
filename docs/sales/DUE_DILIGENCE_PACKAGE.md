# Пакет due diligence

## Индекс материалов

| Вопрос | Документы |
| --- | --- |
| Продукт и scope | [Master Document](../PROJECT_MASTER_DOCUMENT.md), [Feature Catalog](../product/FEATURE_CATALOG.md), [Commercial Scope](COMMERCIAL_SCOPE.md) |
| Доказательства функций | [Feature Evidence Matrix](FEATURE_EVIDENCE_MATRIX.md), [Testing](../engineering/TESTING.md), [API Reference](../engineering/API_REFERENCE.md) |
| Архитектура и данные | [Architecture](../engineering/ARCHITECTURE.md), [Domain Model](../engineering/DOMAIN_MODEL.md), [Database Schema](../engineering/DATABASE_SCHEMA.md) |
| Security/privacy | [Security Overview](../security/SECURITY_OVERVIEW.md), [Threat Model](../security/THREAT_MODEL.md), [Processing Map](../legal/PERSONAL_DATA_PROCESSING_MAP.md) |
| Operations/DR | [Operations Runbook](../operations/OPERATIONS_RUNBOOK.md), [Backup](../operations/BACKUP_AND_RESTORE.md), [DR](../operations/DISASTER_RECOVERY.md) |
| Release readiness | [Production State](../PRODUCTION_STATE.md), [Known Limitations](../KNOWN_LIMITATIONS.md), [Audit](../DOCUMENTATION_AUDIT.md) |
| Legal readiness | [Legal Checklist](../legal/LEGAL_READINESS_CHECKLIST.md), [Customer Documents](../legal/CUSTOMER_DOCUMENTS_REQUIRED.md) |

## Что предоставляется отдельно под NDA

Результаты pentest/scan, dependency reports/SBOM, recovery evidence, incident history, uptime/metrics, договоры с processors, ownership/IP records, финансовые/налоговые материалы и redacted production architecture evidence. Секреты, private keys, реальные `.env`, полные dumps и пользовательские данные не входят в due diligence package.

Каждый пакет маркируется датой, commit/release, владельцем и уровнем конфиденциальности. Утверждения о production подтверждаются отдельными evidences; документация репозитория не подменяет проверку живой среды.
