# Frankfurt Production Notes

This file records the current Frankfurt production posture and the checks that matter before and after deploys. Earlier versions of this document treated Frankfurt as a future target; Frankfurt is now the active production server.

## Current State

| Area | Value |
| --- | --- |
| Provider/location | Aeza Frankfurt |
| SSH alias | `tsplatform-frankfurt` |
| Production path | `/opt/telegram-shop` |
| Production compose | `docker-compose.prod.yml` |
| Production env | `backend/.env.production` |
| Main domain | `https://stylexac.ru` |
| Mini App domain | `https://mini.stylexac.ru` |
| API domain | `https://api.stylexac.ru` |
| Seller Panel domain | `https://seller.stylexac.ru` |
| Current migration head | `20260628_0039` |

## Services

| Service | Runtime |
| --- | --- |
| `backend` | FastAPI/Uvicorn in Docker |
| `postgres` | PostgreSQL 16 in Docker |
| `redis` | Redis 7 in Docker |
| `mini-app` | Built React/Vite static service in Docker |
| `seller-panel` | Built React/Vite static service in Docker |
| Caddy | Host reverse proxy and TLS |
| `telegram-shop-backup.service` | Host systemd backup entry point |
| `tsplatform-mss-clamp.service` | Host systemd MTU compatibility entry point |

## Domain Checks

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://stylexac.ru/
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

## Compose Check

```bash
ssh tsplatform-frankfurt
cd /opt/telegram-shop
docker compose --env-file backend/.env.production -f docker-compose.prod.yml config >/tmp/telegram-shop-compose-check.yml
docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps
```

## Migration Check

```bash
cd /opt/telegram-shop
docker compose --env-file backend/.env.production -f docker-compose.prod.yml run --rm --no-deps backend alembic current
```

Expected current head:

```text
20260628_0039
```

## Reverse Proxy Compatibility

Caddy HTTP/3/QUIC is intentionally disabled. Telegram WebView and some VPN paths are sensitive to MTU behavior, so the host MSS clamp service is part of the production posture.

```bash
sudo ss -tulpn | grep ':443' || true
sudo systemctl status tsplatform-mss-clamp.service --no-pager
sudo iptables -t mangle -S OUTPUT | grep TCPMSS || true
sudo ip6tables -t mangle -S OUTPUT | grep TCPMSS || true
```

Expected rule: TCPMSS `set-mss 1120` for ports `80` and `443`.

## Bot Checks

Bot 1:

- customer `/start`
- customer `/stop`
- service notifications
- campaigns
- channel entry publish/pin

Bot 2:

- seller/admin/auth-related flows

Do not expose bot tokens while checking webhook state.

## Readiness Checklist Before Risky Deploy

- `git status --short` is understood.
- Backup service ran successfully.
- `docker compose config` completed.
- Required services are identified.
- Alembic migration impact is understood.
- Bot 1/Bot 2 responsibilities are unchanged.
- Caddy HTTP/3 remains disabled.
- MSS clamp service remains active.
- Production env values are not copied into notes.
