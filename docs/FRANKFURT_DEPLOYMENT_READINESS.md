# Frankfurt Deployment Readiness

This document prepares TelegramShopPlatform for a future Frankfurt VDS
deployment. It is a readiness checklist only: do not treat it as permission to
deploy, change DNS, rotate tokens, set webhooks, or run production migrations.

## 1. Goal

Move the Telegram Mini App, Seller Panel, backend API, PostgreSQL, Redis, and
uploads volume to a new Frankfurt server while preserving:

- same-origin Mini App and Seller Panel API access through `/api/*`;
- same-origin upload access through `/uploads/*`;
- compatibility with the separate `https://api.stylexac.ru` API domain;
- privacy-safe telemetry from Prompt 3B1;
- compact catalog DTO, ETag, image derivatives, idempotency, and network
  resilience behavior from previous prompts.

## 2. Why Moscow Aeza Was Rejected

The old Moscow provider must not be considered accepted unless it passes the
same preflight below. The project decision is to prefer Frankfurt because the
new host must prove stable outbound HTTPS to Telegram and Docker Registry from
both host and containers, stable public HTTPS ingress, and lower operational
risk for Telegram Mini App users with VPN.

## 3. Server Requirements

- Ubuntu LTS or equivalent Linux supported by Docker and Caddy.
- Stable IPv4 egress to `api.telegram.org:443`.
- IPv6 is useful but not mandatory if IPv4 is stable.
- Public ports `80/tcp` and `443/tcp` open.
- Enough disk for PostgreSQL, uploads, Docker images, and backups.
- Correct NTP/time synchronization.
- Docker Registry and GitHub access from the host.
- Docker container egress to Telegram and neutral HTTPS endpoints.

## 4. URL Configuration Audit

| component | setting/source | current usage | absolute/relative | required change |
| --- | --- | --- | --- | --- |
| Mini App API | `VITE_API_BASE_URL`, `MINI_APP_VITE_API_BASE_URL`, `mini-app/src/shared/api/client.ts` | all Mini App API calls | supports `https://api.stylexac.ru/api/v1` and `/api/v1` | build Frankfurt Mini App with `/api/v1`; keep absolute value for compatibility |
| Seller Panel API | `VITE_API_BASE_URL`, `SELLER_PANEL_VITE_API_BASE_URL`, `seller-panel/src/shared/api/client.ts` | all Seller Panel API calls | supports absolute and `/api/v1` | build Frankfurt Seller Panel with `/api/v1`; keep absolute value for fallback |
| Backend public API base | `PUBLIC_API_BASE_URL` | webhook helpers and public links | absolute origin, no `/api/v1` suffix | keep `https://api.stylexac.ru` for Telegram webhooks and external links |
| Backend uploads | `PUBLIC_UPLOADS_URL` | product/category/tag/banner/receipt DTO URLs | supports `https://api.stylexac.ru/uploads` and `/uploads` | use `/uploads` for same-origin deployment unless external clients require absolute uploads |
| Mini App media | `normalizeAssetUrl`, `resolvePublicMediaUrl` | ProductCard, detail gallery, cart, banners, tags/categories, receipts display | relative uploads stay `/uploads`; absolute uploads stay absolute | no filesystem paths; do not expose private receipt paths beyond existing protected DTOs |
| Seller media | `resolveMediaUrl` | product editor previews, taxonomy, banners, order receipt preview | relative uploads stay `/uploads`; absolute uploads stay absolute | same resolver, no double hostname |
| Telemetry | `mini-app/src/shared/telemetry/client.ts` | `POST /analytics/telemetry` under API base | `/api/v1/analytics/telemetry` or absolute API URL | use relative URL in same-origin mode so no CORS preflight is created by configuration |
| Mini App URL | `PUBLIC_MINI_APP_BASE_URL` | product/customer notification links | absolute | set to `https://mini.stylexac.ru` or `https://stylexac.ru` depending BotFather entry |
| Seller Panel URL | `PUBLIC_SELLER_PANEL_BASE_URL` | seller order/payment links | absolute | set to `https://seller.stylexac.ru` |
| Telegram Bot 1 links | `TELEGRAM_CUSTOMER_BOT_USERNAME`, webhook scripts | Bot 1 start links and webhook setup | absolute API base for webhook | use `https://api.stylexac.ru` when setting webhook |
| Telegram Bot 2 links | `TELEGRAM_SELLER_BOT_USERNAME`, webhook scripts | seller registration, seller notifications, webhooks | absolute API base for webhook | use `https://api.stylexac.ru` when setting webhook |
| Seller edit/order links | `backend/app/events/payloads.py`, `seller_bot/service.py`, `notifications/service.py` | links sent to sellers | absolute Seller Panel URL | keep `PUBLIC_SELLER_PANEL_BASE_URL=https://seller.stylexac.ru` |
| CORS | `CORS_ORIGINS`, `backend/app/main.py` | absolute API domain mode | allowlist only | include `https://stylexac.ru`, `https://www.stylexac.ru`, `https://mini.stylexac.ru`, `https://seller.stylexac.ru`; no wildcard |
| Frontend nginx | `mini-app/nginx.conf`, `seller-panel/nginx.conf` | SPA fallback and hashed asset cache | local container only | Caddy must route `/api/*` and `/uploads/*` before nginx SPA fallback |
| Caddy template | `deploy/caddy/Caddyfile.frankfurt.example` | production reverse proxy example | same-origin and API domain | copy manually to server after review; never edit real server from Codex |
| WebSocket | repository search | no WebSocket runtime found | n/a | if added later, keep upgrade through reverse proxy |

## 5. Same-Origin and Absolute API Modes

Frontend API base supports both:

```text
https://api.stylexac.ru/api/v1
/api/v1
```

Rules:

- empty frontend API base defaults to `/api/v1`;
- trailing slashes are removed;
- duplicated `/api/v1/api/v1` is normalized away;
- invalid protocols such as `ftp://` are rejected;
- same-origin telemetry uses `/api/v1/analytics/telemetry`;
- absolute mode remains compatible with `https://api.stylexac.ru/api/v1`.

## 6. Upload Strategy

Use `PUBLIC_UPLOADS_URL=/uploads` for same-origin deployment. Keep
`PUBLIC_UPLOADS_URL=https://api.stylexac.ru/uploads` only if an external client
requires absolute upload URLs.

Do not change Prompt 2B image semantics:

- product derivatives stay WebP thumbnail/card/detail;
- legacy originals fall back normally;
- category/tag/banner ratios do not change;
- payment receipts keep private/no-store cache behavior;
- no CDN/S3/backfill is part of this step.

## 7. Reverse Proxy Design

Use `deploy/caddy/Caddyfile.frankfurt.example` as the reviewed template.

Expected routing:

- `api.stylexac.ru/*` -> backend.
- `stylexac.ru`, `www.stylexac.ru`, `mini.stylexac.ru`:
  - `/api/*` -> backend;
  - `/uploads/*` -> backend;
  - everything else -> Mini App nginx.
- `seller.stylexac.ru`:
  - `/api/*` -> backend;
  - `/uploads/*` -> backend;
  - everything else -> Seller Panel nginx.

The template uses `handle`, not `handle_path`, so backend receives original
paths such as `/api/v1/products` and `/uploads/products/x.card.webp`.

## 8. Provider Preflight

Run immediately after buying the Frankfurt VDS and before moving the project:

```bash
hostname
hostname -I
ip route
ip -6 route
timedatectl status
curl -4 -I https://api.telegram.org
curl -6 -I https://api.telegram.org
openssl s_client -connect api.telegram.org:443 -servername api.telegram.org </dev/null
curl -I https://github.com
curl -I https://registry-1.docker.io/v2/
sudo ufw status verbose || true
sudo nft list ruleset || true
df -h
free -h
nproc
```

Acceptance criteria:

- Telegram Bot API is stable over IPv4 from host and Docker.
- A series of 20-50 Telegram public HTTPS checks has no intermittent timeout.
- Docker Registry and GitHub are reachable.
- Outbound HTTPS is not filtered.
- Server time is synchronized.
- Public ports 80/443 are reachable.
- DNS can point to the server.
- Caddy can obtain certificates.

## 9. Docker Egress Checks

After Docker installation and before deployment:

```bash
docker run --rm curlimages/curl:latest -4 -I https://api.telegram.org
docker run --rm curlimages/curl:latest -6 -I https://api.telegram.org || true
docker run --rm curlimages/curl:latest -I https://github.com
docker run --rm curlimages/curl:latest -I https://registry-1.docker.io/v2/
```

After backend container exists:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend \
  python scripts/check_production_connectivity.py \
  --api-base-url https://api.stylexac.ru/api/v1 \
  --mini-app-url https://mini.stylexac.ru \
  --seller-panel-url https://seller.stylexac.ru \
  --telegram-public --ip-mode ipv4
```

Print only proxy environment variable names, never values:

```bash
env | grep -Ei '^(http|https|all)_proxy=' | cut -d= -f1
```

## 10. DNS Records

Create or update only during the planned cutover window:

```text
stylexac.ru         A     <Frankfurt IPv4>
www.stylexac.ru     A     <Frankfurt IPv4>
mini.stylexac.ru    A     <Frankfurt IPv4>
seller.stylexac.ru  A     <Frankfurt IPv4>
api.stylexac.ru     A     <Frankfurt IPv4>
```

Add AAAA only after IPv6 egress/ingress is proven stable.

## 11. Required Environment Variables

Do not put values in this document. Required names:

```text
APP_ENV
DEBUG
DATABASE_URL
REDIS_URL
JWT_SECRET_KEY
CORS_ORIGINS
PUBLIC_API_BASE_URL
PUBLIC_UPLOADS_URL
PUBLIC_MINI_APP_BASE_URL
PUBLIC_SELLER_PANEL_BASE_URL
TELEGRAM_WEBAPP_BOT_TOKEN
TELEGRAM_BOT_TOKEN
TELEGRAM_SELLER_CHAT_ID
TELEGRAM_SELLER_BOT_USERNAME
TELEGRAM_SELLER_WEBHOOK_SECRET
TELEGRAM_CUSTOMER_BOT_TOKEN
TELEGRAM_CUSTOMER_BOT_USERNAME
TELEGRAM_CUSTOMER_WEBHOOK_SECRET
MINI_APP_VITE_API_BASE_URL
SELLER_PANEL_VITE_API_BASE_URL
VITE_TELEGRAM_BOT_USERNAME
TELEMETRY_ENABLED
BACKUP_* and YANDEX_* variables from backup docs
```

## 12. Secrets Rotation Checklist

- Generate new `JWT_SECRET_KEY`.
- Generate webhook secrets for Bot 1 and Bot 2.
- Rotate Telegram tokens only through BotFather during a planned operation.
- Store database, Redis, Yandex, Telegram, and JWT secrets outside git.
- Never paste `.env.production` into tickets, prompts, or logs.

## 13. Docker and Caddy Installation

Install Docker Engine and Compose plugin from official packages for the target
OS. Install Caddy from official packages. Validate:

```bash
docker version
docker compose version
caddy version
caddy validate --config /etc/caddy/Caddyfile
```

## 14. Database Strategy

Use a fresh PostgreSQL database from migrations unless a production data
migration plan exists. Migration order includes:

```text
20260624_0034_add_idempotency_records
20260624_0035_add_product_image_derivatives
20260625_0036_add_privacy_safe_telemetry
future head
```

Run:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend alembic current
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend alembic heads
```

## 15. Build Order

1. Prepare `.env.production` from examples.
2. Build backend.
3. Build Mini App with `MINI_APP_VITE_API_BASE_URL=/api/v1`.
4. Build Seller Panel with `SELLER_PANEL_VITE_API_BASE_URL=/api/v1`.
5. Start PostgreSQL/Redis/backend.
6. Run Alembic.
7. Start frontends.
8. Put Caddy in front.

## 16. Local Loopback Smoke

Before public DNS:

```bash
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1:8000/api/v1/products
curl -i http://127.0.0.1:8081
curl -i http://127.0.0.1:8080
```

## 17. Public HTTPS Smoke

After Caddy and DNS:

```bash
curl -i https://api.stylexac.ru/health
curl -i https://api.stylexac.ru/api/v1/products
curl -i https://mini.stylexac.ru
curl -i https://mini.stylexac.ru/api/v1/products
curl -i https://mini.stylexac.ru/uploads/missing.webp
curl -i https://seller.stylexac.ru
curl -i https://seller.stylexac.ru/api/v1/products
```

API/upload 404 must be JSON from backend, not frontend HTML.

## 18. Cache and ETag Tests

```bash
curl -i https://mini.stylexac.ru/assets/<hashed>.js
curl -i https://api.stylexac.ru/api/v1/products?limit=1
curl -i -H 'If-None-Match: "<etag>"' https://api.stylexac.ru/api/v1/products?limit=1
curl -i https://api.stylexac.ru/uploads/products/<sample>.card.webp
```

Expected:

- hashed frontend assets: `public, max-age=31536000, immutable`;
- `index.html`: `no-cache`;
- product/tags/categories/banners include ETag where implemented;
- payment receipts are never public immutable.

## 19. Synthetic Checker

Host run:

```bash
cd backend
python scripts/check_production_connectivity.py \
  --api-base-url https://api.stylexac.ru/api/v1 \
  --mini-app-url https://mini.stylexac.ru \
  --seller-panel-url https://seller.stylexac.ru \
  --uploads-test-url https://api.stylexac.ru/uploads/products/<sample>.card.webp \
  --telegram-public \
  --format human
```

JSON output:

```bash
python scripts/check_production_connectivity.py ... --format json
```

Telegram bot token checks:

```bash
TELEGRAM_BOT_TOKEN=<from secret store> \
python scripts/check_production_connectivity.py ... --telegram-bot-env TELEGRAM_BOT_TOKEN
```

Tokens are read only from environment variables and are redacted from output.
The checker does not call `setWebhook`, `deleteWebhook`, send messages, or
mutate catalog/order/payment/user data.

## 20. Latency Measurement Points

Measure DNS, TCP, TLS, TTFB, and total duration from:

- the Frankfurt server host;
- inside the backend container;
- the developer's local machine;
- VPN Germany;
- VPN Netherlands;
- if possible, no-VPN connection from Russia.

Do not infer user geography or business logic from IP.

## 21. Telemetry Production Validation

After deployment, verify Prompt 3B1 safely:

- valid telemetry batch returns `202`;
- forbidden field returns `422`;
- rate limit does not block normal batches;
- Telegram WebView sends `sendBeacon`;
- fallback `fetch(..., keepalive)` works;
- `X-Request-ID` correlates frontend/backend errors;
- route and Web Vitals events appear;
- retry and 304 events appear under sampling;
- checkout/payment timeout simulation records ambiguous outcome without a
  second mutation;
- receipt upload duration appears without receipt path/content;
- retention dry-run works;
- rows contain no forbidden data.

Safe aggregate SQL examples:

```sql
SELECT event_name, count(*)
FROM analytics_events
WHERE event_version = 1
  AND created_at >= now() - interval '24 hours'
GROUP BY event_name
ORDER BY count(*) DESC;

SELECT event_name,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95
FROM analytics_events
WHERE event_version = 1
  AND duration_ms IS NOT NULL
  AND created_at >= now() - interval '24 hours'
GROUP BY event_name;
```

No raw metadata export is needed for readiness.

## 22. Webhook Cutover

Do not set webhooks until the new backend is reachable from Telegram.

Safe order:

1. Prove new backend public HTTPS.
2. Run Bot 1/Bot 2 `getMe`.
3. Run current `getWebhookInfo`.
4. Stop old backend or old Telegram processing.
5. Set Bot 2 webhook.
6. Verify Bot 2 `getWebhookInfo`.
7. Set Bot 1 webhook.
8. Verify Bot 1 delivery.
9. Verify `/start`.
10. Verify Bot 2 `/help`.
11. Verify callbacks.
12. Check logs and request IDs.
13. Mark cutover complete only after delivery is stable.

## 23. BotFather Mini App/Menu URL

After HTTPS smoke, set Mini App/Menu URL to the selected public Mini App origin,
for example:

```text
https://mini.stylexac.ru
```

Do not configure BotFather before the domain is reachable over HTTPS.

## 24. First Telegram Login

Open the Mini App through Telegram. Verify `/users/me` and request IDs. Do not
bootstrap ADMIN automatically.

## 25. ADMIN Bootstrap

Actual enum values are `USER`, `SELLER`, `ADMIN`.

Safe manual algorithm:

1. Open Mini App through Telegram.
2. Ensure exactly the expected user was created.
3. Select only safe identifying fields, for example id, telegram_id,
   telegram_username, role, created_at.
4. Manually verify Telegram ID.
5. Update only that user's role to `ADMIN`.
6. Never use "first user becomes ADMIN".
7. Abort if user count differs from expectation.
8. Close/reopen Mini App so JWT is refreshed.
9. Verify `/api/v1/users/me`.
10. Create an audit record if the audit layer is available for the manual
    operation.

## 26. Seller Credentials and SBP Settings

Create seller credentials only after ADMIN bootstrap. Configure SBP settings in
Seller Panel and verify a test checkout/payment flow without real money.

## 27. Backup Readiness

Before traffic:

- run first manual backup;
- verify checksums;
- upload to Yandex Disk;
- perform restore drill into a temporary database;
- install systemd timer only after manual backup succeeds;
- enable Telegram backup notifications only after Telegram connectivity works;
- backup failures must be visible in logs even if Telegram notification fails.

Backup must cover PostgreSQL, uploads volume, idempotency table, telemetry
table, image derivative paths, and fresh migrations. Redis remains cache/rate
limit state and is not durable data.

## 28. Rollback

Rollback options:

- keep old server read-only until new server observation period passes;
- route DNS back only if old backend and DB are authoritative;
- do not split writes between old and new servers;
- keep uploads and DB snapshots from before cutover.

## 29. Old Server Read-Only Retention

After successful cutover, keep old server read-only for the agreed period. Do
not run Telegram processing on both servers.

## 30. Manual QA

Run Mini App and Seller Panel QA from:

- Frankfurt server smoke;
- VPN Germany;
- VPN Netherlands;
- if possible, no-VPN Russia.

Check feed startup, search, product detail, cart, checkout, payment submit,
receipt upload, favorite toggles, chunk recovery, and Web Vitals telemetry.

## 31. Post-Deploy Observation

Observe for at least several hours:

- API 5xx and timeouts;
- Telegram webhook delivery;
- checkout/payment ambiguous outcomes;
- receipt upload failures;
- chunk recovery failures;
- Web Vital p75/p95;
- 304 ratio;
- Caddy logs;
- disk growth for uploads and telemetry.

## 32. Acceptance Checklist

- [ ] Provider preflight passed with repeated checks.
- [ ] Docker host and container egress passed.
- [ ] Caddy validates.
- [ ] DNS points to Frankfurt.
- [ ] Caddy certificates issued.
- [ ] `alembic upgrade head/current/heads` passed.
- [ ] Mini App same-origin API works.
- [ ] Seller Panel same-origin API works.
- [ ] `api.stylexac.ru` works.
- [ ] `/api` and `/uploads` never fall through to SPA HTML.
- [ ] Cache/ETag checks passed.
- [ ] Synthetic checker passed.
- [ ] Telegram getMe/getWebhookInfo passed for both bots.
- [ ] Webhook cutover passed.
- [ ] First Telegram login passed.
- [ ] ADMIN bootstrap completed manually and safely.
- [ ] Seller credentials and SBP settings verified.
- [ ] Manual backup and restore drill passed.
- [ ] Germany/Netherlands VPN QA passed.
- [ ] Observation period completed without blocking issues.
