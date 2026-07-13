# Состояние production

Статус: канонический снимок. Последняя проверка: 2026-07-13. Конфиденциальность: Internal.

## Подтвержденный релиз

| Объект | Состояние на момент приемки |
| --- | --- |
| Git | `main`, `325e3af2a79dd9d4af92050e272169828d0edfbf` |
| Alembic | `20260713_0056` |
| Backend container | healthy |
| `https://stylexac.ru` | HTTP 200 |
| `https://mini.stylexac.ru` | HTTP 200 |
| `https://api.stylexac.ru/health` | HTTP 200 |
| `https://seller.stylexac.ru` | HTTP 200 |
| PostgreSQL / Redis | продолжали работать во время релиза |
| Migration path | `20260712_0054` → `20260712_0055` → `20260713_0056` |
| Backup | новый local backup создан; restore verification passed |
| Remote upload этого backup | `skipped` |
| Notification backfill | исторический backfill не выполнялся |

Снимок не является SLA, uptime guarantee или доказательством текущей доступности после даты
проверки. Проверки production в рамках документационного аудита не выполнялись.

## Топология

Host reverse proxy публикует backend, Mini App и Seller Panel. Compose содержит `backend`,
`mini-app`, `seller-panel`, PostgreSQL 16 и Redis 7. Uploads, PostgreSQL и Redis используют
отдельные volumes. Production path — `/opt/telegram-shop`.

Источник: `docker-compose.prod.yml`, `deploy/caddy/Caddyfile.frankfurt.example`,
`backend/alembic/versions/20260713_0056_add_customer_in_app_notifications.py`.

## Известный operational drift

Репозиторный `scripts/systemd/telegram-shop-backup.service` использует устаревший путь
`/opt/TelegramShopPlatform`. Его нельзя устанавливать verbatim для текущего production path.

**NEEDS VERIFICATION** — фактическое содержимое установленного unit на host не проверялось,
потому что production access запрещен. Нужен operator с доступом к host и выводом
`systemctl cat telegram-shop-backup.service` без secret values. Это блокирует безопасную
переустановку unit, но не опровергает подтвержденный успешный backup.

Canonical deployment: [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md).

