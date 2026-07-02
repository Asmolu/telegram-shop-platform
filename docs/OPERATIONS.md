# Operations

This document covers routine production operations for StyleXac.

## Production Facts

| Area | Value |
| --- | --- |
| Server | Aeza Frankfurt |
| SSH alias | `tsplatform-frankfurt` |
| Project path | `/opt/telegram-shop` |
| Compose file | `docker-compose.prod.yml` |
| Env file | `backend/.env.production` |
| Main domain | `https://stylexac.ru` |
| API health | `https://api.stylexac.ru/health` |
| Mini App | `https://mini.stylexac.ru/` |
| Seller Panel | `https://seller.stylexac.ru/` |
| Current migration head | `20260628_0039` |

## Daily Status Check

```bash
ssh tsplatform-frankfurt
cd /opt/telegram-shop
git status --short
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

## Logs

```bash
cd /opt/telegram-shop
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=200 backend
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 mini-app
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 seller-panel
```

Do not paste logs publicly if they contain customer data, Telegram identifiers, stack traces with request metadata, or environment values.

## Backup

Use the systemd backup service on production. Do not run a bare Python backup command on the production host unless the service itself is broken and the fallback is explicitly approved.

```bash
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
```

Always run a backup before Alembic migrations.

Backup Telegram notifications use `TELEGRAM_BACKUP_CHAT_ID`. `TELEGRAM_SELLER_CHAT_ID` is only a legacy fallback while production env files are migrated.

## Deployment

The full deployment flow is documented in `docs/PRODUCTION_DEPLOYMENT.md`. The short version:

```bash
ssh tsplatform-frankfurt
cd /opt/telegram-shop
git status --short
git fetch origin
git pull --ff-only origin main
docker compose --env-file backend/.env.production -f docker-compose.prod.yml config >/tmp/telegram-shop-compose-check.yml
sudo systemctl start telegram-shop-backup.service
docker compose --env-file backend/.env.production -f docker-compose.prod.yml build backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic upgrade head
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic current
docker compose --env-file backend/.env.production -f docker-compose.prod.yml up -d backend mini-app seller-panel
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
```

If the production host does not have a `python` command, use the backend Docker container or the project virtual environment for backend commands.

## MTU, VPN, and Telegram Compatibility

Caddy listens on TCP `:443`. HTTP/3/QUIC is intentionally disabled. The MSS clamp service is intentionally active.

```bash
sudo ss -tulpn | grep ':443' || true
sudo systemctl status tsplatform-mss-clamp.service --no-pager
sudo iptables -t mangle -S OUTPUT | grep TCPMSS || true
sudo ip6tables -t mangle -S OUTPUT | grep TCPMSS || true
```

Expected MSS rule: TCPMSS clamp for ports `80` and `443` with `set-mss 1120`.

## Reverse Proxy

Host Caddy routes:

- `https://api.stylexac.ru` to backend on localhost
- `https://mini.stylexac.ru` to Mini App container
- `https://seller.stylexac.ru` to Seller Panel container
- `https://stylexac.ru` to the Mini App entry
- uploads through backend/reverse proxy

HTTP/3/QUIC must stay disabled unless a production compatibility test proves it is safe for Telegram WebView and VPN users.

## Sensitive Data Handling

- Never print full `backend/.env.production`.
- Never paste raw bot tokens, JWT secrets, database passwords, Yandex Disk tokens, private keys, or production credentials into docs.
- Validate Telegram webhook secrets without exposing their values.
- Check secret presence with targeted commands that print only variable names or boolean state.

## Incident Notes

During an incident, capture:

- exact UTC or Moscow time window
- affected domain
- affected service
- last deployed commit
- current migration from `alembic current`
- Docker service status
- relevant backend log window with secrets removed
- customer-visible symptom
- rollback or fix applied
