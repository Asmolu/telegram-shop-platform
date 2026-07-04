# Production Deployment

This document is the current production deploy runbook for StyleXac.

## Current Production Context

| Area | Value |
| --- | --- |
| Server | Aeza Frankfurt |
| SSH alias | `tsplatform-frankfurt` |
| Project path | `/opt/telegram-shop` |
| Compose file | `docker-compose.prod.yml` |
| Env file | `backend/.env.production` |
| Main domain and Mini App entry | `https://stylexac.ru` |
| Mini App direct domain | `https://mini.stylexac.ru` |
| API domain | `https://api.stylexac.ru` |
| Seller Panel domain | `https://seller.stylexac.ru` |
| Current migration head | `20260703_0047` |

The production stack contains `backend`, `postgres`, `redis`, `mini-app`, and `seller-panel`. Host Caddy terminates TLS and reverse-proxies to the containers.

## Environment Convention

- `.env` is for local development and local checks.
- `backend/.env.production` is for VDS/server work and production-domain checks.
- Do not copy real production env values into documentation.
- Use placeholders only: `<SECRET>`, `<BOT_TOKEN>`, `<DATABASE_URL>`, `<JWT_SECRET>`.

## Before Deploying

1. Confirm the target commit and changed services.
2. Confirm whether Alembic migrations are present.
3. Run and verify a backup before any migration.
4. Avoid deploys while a customer campaign is actively sending unless the campaign can be paused.
5. Confirm Bot 1 and Bot 2 tokens remain assigned to their correct responsibilities.

## Deploy Flow

```bash
ssh tsplatform-frankfurt
cd /opt/telegram-shop
git status --short
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 160 --no-pager
git fetch origin
git pull --ff-only origin main
docker compose --env-file backend/.env.production -f docker-compose.prod.yml build backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend alembic upgrade head
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend alembic current
docker compose --env-file backend/.env.production -f docker-compose.prod.yml up -d backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
```

If only a subset of services changed, build and restart only that subset after confirming the dependency impact. When a migration exists, run the migration before restarting traffic-facing services.

## Mandatory Backup Before Migration

Production backups are managed through systemd:

```bash
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 160 --no-pager
```

Use the systemd service on production. Do not use a bare Python backup command on the host for normal production deploys.
Do not deploy migrations if the backup fails.

## Migration Checks

Current production head after the latest deploy is:

```text
20260703_0047
```

Check the current database revision after migration:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm backend alembic current
```

If the host does not have a `python` command, use the backend Docker container or the project virtual environment for checks.

## Smoke Checks

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

Expected result:

- API health returns `2xx`.
- Mini App returns a browser-loadable HTML response.
- Seller Panel returns a browser-loadable HTML response.

## Log Checks

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=250 backend
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 mini-app
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 seller-panel
```

Check for:

- backend startup errors
- migration errors
- Telegram webhook errors
- upload path errors
- Redis connectivity errors
- frontend asset serving errors
- customer notification delivery failures after checkout tests

Do not paste logs containing real secrets or raw production env values.

## Service Map

| Compose service | Purpose | Public exposure |
| --- | --- | --- |
| `backend` | FastAPI API, uploads, bot webhooks, background workers | Through `https://api.stylexac.ru` |
| `postgres` | PostgreSQL 16 database | Internal Docker network |
| `redis` | Redis 7 cache/rate-limit/temporary state store | Internal Docker network |
| `mini-app` | Built Mini App static service | Through `https://mini.stylexac.ru` and `https://stylexac.ru` |
| `seller-panel` | Built Seller Panel static service | Through `https://seller.stylexac.ru` |

Old `tsplatform.ru` domains are not current production domains. Current public production uses the `stylexac.ru` domain family.

## Telegram Bot Checks

Bot 1:

- customer `/start`
- customer `/stop`
- service notifications
- customer campaigns
- channel entry publish/pin

Bot 2:

- seller/admin/auth-related flows

After deploy, verify Bot 1 and Bot 2 webhooks only through safe operational checks. Do not print bot tokens.

## Customer Notification Checks

For notification-related deploys, verify:

- Bot 1 `/start` creates or updates `CustomerTelegramSubscription`.
- Bot 1 `/stop` disables service and marketing eligibility.
- Mini App write-access action calls `requestWriteAccess()` only after a user action.
- `POST /api/v1/customer-notifications/me/write-access` persists grant or denial.
- Service notification send prefers `telegram_chat_id` and can use `telegram_user_id` when write access is granted and no private chat exists.
- Campaign delivery reports remain accessible in Seller Panel.

## Channel Entry Checks

For channel-entry deploys, verify:

- Seller Panel `/channel-entry` loads.
- Publish uses Bot 1.
- Channel button is a URL button.
- Link uses `startapp=channel_pin` unless overridden by `TELEGRAM_CHANNEL_ENTRY_START_PARAM`.
- History stores Telegram `message_id` and pin status.

Do not test publish/pin in a production customer channel unless that channel is approved for operational tests.

## Returns, Looks, Feed, and Alias Checks

For the current release, verify:

- hidden active products are absent from public lists but open by direct link
- return requests with media notify the returns Telegram group
- return approve/reject callbacks work only from the returns group and only for seller/admin identities
- refund/restock processing records manual refund details and restocks only selected quantities
- Looks with clothing and footwear components require separate size selections
- Look-sourced cart/order items remain grouped in Mini App and Seller Panel order detail
- old product/category/Look slugs resolve and canonicalize
- `GET /api/v1/feed` returns both product and Look items when both exist

## Caddy and MTU Checks

Caddy uses TCP `:443`; HTTP/3/QUIC is intentionally disabled. The MSS clamp service is intentionally enabled.

```bash
sudo ss -tulpn | grep ':443' || true
sudo systemctl status tsplatform-mss-clamp.service --no-pager
sudo iptables -t mangle -S OUTPUT | grep TCPMSS || true
sudo ip6tables -t mangle -S OUTPUT | grep TCPMSS || true
```

Expected rule: TCPMSS `set-mss 1120` for ports `80` and `443`.

## Rollback

Rollback depends on whether a migration was applied.

If no migration was applied:

```bash
cd /opt/telegram-shop
git log --oneline -5
git checkout <PREVIOUS_SAFE_COMMIT>
docker compose --env-file backend/.env.production -f docker-compose.prod.yml build backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml up -d backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
```

If a migration was applied:

1. Stop and assess before downgrading.
2. Confirm the backup created before migration is usable.
3. Determine whether Alembic downgrade is safe for the specific migration.
4. Prefer forward-fix when customer data would be lost by downgrade.
5. Restore from backup only after explicit operational approval.

Do not run destructive database commands without an approved rollback plan.

## Post-Deploy Record

Record:

- deployed commit
- services rebuilt
- Alembic revision after deploy
- backup job status
- smoke check results
- relevant log status
- any Telegram/customer notification verification performed
