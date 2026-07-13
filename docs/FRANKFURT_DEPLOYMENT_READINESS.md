# Готовность Frankfurt production

**Подтвержденный snapshot:** Aeza Frankfurt, path `/opt/telegram-shop`, commit `325e3af`, Alembic `20260713_0056`, 13 июля 2026 года. Main/Mini/API/Seller domains семейства `stylexac.ru` отвечали HTTP 200, backend был healthy, PostgreSQL/Redis оставались запущены.

Перед следующим релизом повторно проверить clean host worktree, approved commit, compose config, migrations, campaign state, disk, backup service/restore evidence, domains/TLS, Bot 1/Bot 2, workers/outbox, monitoring/contacts и rollback owner. Fresh local backup и restore verification были успешны в подтвержденном релизе; конкретный remote upload был skipped. Это не освобождает от новой проверки.

Repository systemd backup template содержит устаревший `/opt/TelegramShopPlatform`; installed unit должен использовать `/opt/telegram-shop`. Точные команды и gates — [Production Deployment](PRODUCTION_DEPLOYMENT.md), риски — [Production State](PRODUCTION_STATE.md) и [Known Limitations](KNOWN_LIMITATIONS.md). Этот документ не разрешает подключение к host или deployment.
