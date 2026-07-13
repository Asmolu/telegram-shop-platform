# Security review

**Срез:** commit `325e3af`, Alembic `20260713_0056`, 13 июля 2026 года. Канонический пакет: [Security Overview](security/SECURITY_OVERVIEW.md), [Threat Model](security/THREAT_MODEL.md), [Security Checklist](security/SECURITY_CHECKLIST.md).

Подтвержденные code-level controls: server-side HMAC/freshness Telegram `initData`, запрет raw auth material в storage/logs, RBAC и store scope, audit критических действий, Redis rate limiting с memory fallback, transactional checkout/stock, durable outbox, разделение Bot 1/Bot 2, backup с restore verification.

Открытые gates: независимый pentest и IDOR/BOLA review, production IAM/secrets rotation, edge/security headers, malware scanning/quarantine uploads, SCA/SBOM, alerting, retention/privacy и legal sign-off. Поэтому состояние нельзя описывать как сертифицированное или полностью security-approved. Результаты проверки фиксируются для конкретного release; секреты и персональные данные в отчет не включаются.
