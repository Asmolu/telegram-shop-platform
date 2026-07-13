# Развертывание в production

**Класс:** внутренний restricted runbook. **Подтвержденный срез:** commit `325e3af`, Alembic `20260713_0056`, 13 июля 2026 года. Документ не является разрешением на deployment.

## Целевая среда

| Параметр | Значение |
| --- | --- |
| Host | Aeza Frankfurt |
| SSH alias | `tsplatform-frankfurt` |
| Путь | `/opt/telegram-shop` |
| Compose | `docker-compose.prod.yml` |
| Env | `backend/.env.production` |
| Main / Mini / API / Seller | `https://stylexac.ru` / `https://mini.stylexac.ru` / `https://api.stylexac.ru` / `https://seller.stylexac.ru` |
| Текущий head | `20260713_0056` |

Секретные значения не печатать и не переносить в Git. Production env отличается от локальной `.env`. Все команды выполняются оператором на production host только после утверждения change/release.

## Gates до подключения

- утверждены commit, scope, окно, владелец и rollback decision maker;
- CI и релевантные тесты зелены;
- migration chain и data-loss impact рассмотрены;
- worktree на host чистый; локальные артефакты исключены через `.git/info/exclude`, а не коммит;
- активные campaigns остановлены или безопасно завершаются;
- backup и restore verification запланированы;
- Bot 1/Bot 2, домены, storage и monitoring имеют владельцев;
- команда не вставляется одним огромным буфером: оператор выполняет фазы по отдельности и проверяет результат.

## Последовательность

### 1. Состояние кода

```bash
ssh tsplatform-frankfurt
cd /opt/telegram-shop
git status --short
git fetch origin
git pull --ff-only origin main
git rev-parse HEAD
```

HEAD должен совпасть с утвержденным release commit. При неожиданном изменении worktree deployment прекращается.

### 2. Проверка Compose и backup

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml config >/tmp/telegram-shop-compose-check.yml
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
```

Проверить успешное создание локальной копии и restore verification. Remote upload может быть пропущен политикой cadence; это фиксируется в release record, а не трактуется как локальная ошибка. Не использовать устаревший unit template path `/opt/TelegramShopPlatform` без исправления установленного unit: текущий путь — `/opt/telegram-shop`.

### 3. Сборка

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml build backend mini-app seller-panel
```

### 4. Миграции

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic heads
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic current
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic upgrade head
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic current
```

Ожидаемый head этого среза — `20260713_0056`. Ревизии `20260712_0055` и `20260713_0056` уже входят в подтвержденный migration path; их data effects нельзя откатывать нерассмотренным downgrade. PostgreSQL и Redis не перезапускаются без отдельной необходимости.

### 5. Запуск приложений

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml up -d backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
```

### 6. Проверка

```bash
curl -fsS https://api.stylexac.ru/health
curl -fsSI https://stylexac.ru
curl -fsSI https://mini.stylexac.ru
curl -fsSI https://seller.stylexac.ru
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=200 backend
```

Дополнительно вручную проверить Mini App auth/catalog/checkout, Seller login/order, Bot 1 customer flow, Bot 2 seller/auth flow, payment state, outbox/in-app notifications и отсутствие утечки raw `initData`/секретов в логах. Не запускать реальную campaign и не публиковать channel entry как часть smoke без отдельного разрешения.

## Решение после deployment

При успехе записать commit, revision, images, время, backup/restore evidence, health/smoke, отклонения и оператора. При ошибке остановиться на безопасной фазе и использовать [Rollback](operations/ROLLBACK.md) и [Incident Response](operations/INCIDENT_RESPONSE.md). По умолчанию предпочтителен forward fix; database downgrade допускается только после анализа необратимых изменений и восстановления из проверенной копии.

Подтвержденный релиз 13 июля 2026 года завершился healthy backend, HTTP 200 для трех web entry и API health, с PostgreSQL/Redis без остановки, свежим локальным backup и успешной restore verification; конкретный pre-deploy remote upload был skipped. Это исторический факт, не гарантия будущего uptime.
