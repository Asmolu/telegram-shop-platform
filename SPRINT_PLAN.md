# Sprint Plan and Delivery Record

This file is the current delivery record and forward checklist for StyleXac. Historical sprint names are kept only as delivery context; current production behavior is documented in the linked operational docs.

## Current Production Baseline

| Area | Value |
| --- | --- |
| Production domains | `stylexac.ru`, `mini.stylexac.ru`, `api.stylexac.ru`, `seller.stylexac.ru` |
| Server | Aeza Frankfurt |
| Path | `/opt/telegram-shop` |
| Compose | `docker-compose.prod.yml` |
| Env | `backend/.env.production` |
| Current migration head | `20260703_0047` |

## Delivered Platform Areas

| Area | Status |
| --- | --- |
| FastAPI backend scaffold | Delivered |
| SQLAlchemy async models and Alembic migrations | Delivered |
| PostgreSQL and Redis integration | Delivered |
| Telegram Mini App auth | Delivered |
| JWT/session handling | Delivered |
| User roles `USER`, `SELLER`, `ADMIN` | Delivered |
| Categories, tags, products | Delivered |
| Product images/uploads | Delivered |
| Product variants and inventory | Delivered |
| Product search aliases and priority | Delivered |
| Product visibility, returnability, and size groups | Delivered |
| Multi-category product assignments | Delivered |
| Cart and checkout | Delivered |
| Order snapshots and stock decrement | Delivered |
| Return requests, lifecycle, refund/restock | Delivered |
| Looks/outfits and grouped Look cart/order items | Delivered |
| Mixed product/Look feed | Delivered |
| Route aliases for products, categories, and Looks | Delivered |
| Promo codes and coupon usage | Delivered |
| Manual payment flows | Delivered |
| Reviews with moderation | Delivered |
| Banners including popup and aggressive popup | Delivered |
| Analytics events where implemented | Delivered |
| Customer notification subscriptions | Delivered |
| Bot 1 write-access service notification flow | Delivered |
| Customer campaigns and delivery reports | Delivered |
| Seller Panel product management | Delivered |
| Seller Panel banners and promo codes | Delivered |
| Seller Panel customer notifications | Delivered |
| Seller Panel channel entry | Delivered |
| Bot 1 customer/channel flows | Delivered |
| Bot 2 seller/admin/auth flows | Delivered |
| Aeza Frankfurt production deployment | Delivered |
| Caddy host reverse proxy | Delivered |
| HTTP/3/QUIC disabled for compatibility | Delivered |
| TCP MSS clamp service | Delivered |
| Systemd production backup service | Delivered |

## Current Sprint Focus

Documentation and operational accuracy:

- keep documentation aligned with production domains and deployment flow
- preserve Bot 1/Bot 2 separation in docs and code
- keep write-access notification behavior explicit
- keep channel entry behavior explicit
- keep deployment, backup, MTU, and smoke-check commands current
- avoid documenting features that are not implemented

## Follow-Up Verification Backlog

These are verification targets, not promises of new functionality:

| Area | Verification |
| --- | --- |
| Customer notifications | Re-run focused backend tests after notification changes |
| Channel entry | Confirm URL button payload and history persistence after channel changes |
| Campaigns | Confirm campaign image send, preview, test send, and report counters |
| Checkout | Confirm order transaction, stock decrement, coupon usage, and post-commit notifications |
| Uploads | Confirm image profile validation and public serving |
| Caddy/MTU | Confirm HTTP/3 remains disabled and MSS clamp remains active |
| Backups | Confirm systemd backup status before migrations |

## Release Checklist

Before production deploy:

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

Smoke checks:

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

Logs:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=250 backend
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 mini-app
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=120 seller-panel
```

## Documentation Links

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/PRODUCTION_DEPLOYMENT.md`
- `docs/OPERATIONS.md`
- `docs/CUSTOMER_NOTIFICATIONS_ARCHITECTURE.md`
- `docs/TELEGRAM_CHANNEL_ENTRY.md`
- `docs/TESTING.md`
- `UI_DESIGN_SPEC.README.md`
