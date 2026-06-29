# Backup and Restore

This document describes production backup and restore procedures for StyleXac.

## Production Context

| Area | Value |
| --- | --- |
| Server | Aeza Frankfurt |
| SSH alias | `tsplatform-frankfurt` |
| Project path | `/opt/telegram-shop` |
| Compose file | `docker-compose.prod.yml` |
| Env file | `backend/.env.production` |
| Database service | `postgres` |
| Upload storage | Docker volume mounted to backend uploads directory |

## Backup Rule

Run a backup before every Alembic migration and before any operation that could affect database or upload integrity.

On production, use the systemd service:

```bash
ssh tsplatform-frankfurt
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
```

Do not run a bare Python backup command on production for normal operations. Use the service because it captures the production paths, env, permissions, logging, and operational wrapper expected on the server.

## What Must Be Backed Up

| Data | Why it matters |
| --- | --- |
| PostgreSQL database | Orders, users, subscriptions, catalog, coupons, campaigns, audit logs |
| Uploads volume | Product images, banner images, campaign images, review images, payment receipts |
| Deployment metadata | Commit, migration head, compose file identity |

The production env file itself contains secrets and must be protected separately. Do not include raw env values in shared backup reports.

## Pre-Migration Backup

```bash
ssh tsplatform-frankfurt
cd /opt/telegram-shop
git status --short
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic current
```

Expected current production migration after the latest deploy:

```text
20260628_0039
```

## Restore Principles

1. Stop and identify the incident scope.
2. Preserve the broken state long enough to diagnose whether restore is needed.
3. Confirm the backup timestamp, database revision, and upload archive identity.
4. Prefer forward-fix when a migration has already changed customer data in a way that cannot be safely downgraded.
5. Restore database and uploads as a matched set when file paths changed.
6. Do not print secrets while verifying restore commands.

## Restore Checklist

Before restore:

- confirm affected domains
- confirm affected services
- record current commit
- record `alembic current`
- record `docker compose ps`
- identify the backup to restore
- confirm whether new orders or uploads happened after the backup
- get explicit approval for data loss if restoring to an older state

After restore:

- run `alembic current`
- run API health check
- open Mini App
- open Seller Panel
- verify uploads render
- verify order/customer notification pages load
- inspect backend logs

## Health Checks After Restore

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

## Log Checks After Restore

```bash
cd /opt/telegram-shop
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=200 backend
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 mini-app
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 seller-panel
```

## Sensitive Data Rules

- Do not store backups in a public bucket.
- Do not paste backup archive names if they reveal private infrastructure naming.
- Do not paste `backend/.env.production`.
- Do not include DB passwords, bot tokens, JWT secrets, Yandex Disk tokens, or private keys in restore notes.
