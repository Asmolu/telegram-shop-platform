# Analytics and Telemetry

Analytics and telemetry capture product usage, banner interaction, and selected frontend diagnostics without storing raw secrets or raw Telegram `initData`.

## Implemented Areas

| Area | Implementation |
| --- | --- |
| Backend model | `AnalyticsEvent` in SQLAlchemy models |
| Backend module | `backend/app/modules/analytics` |
| Mini App client | telemetry client under `mini-app/src/shared/telemetry` |
| Banner analytics | banner view and click events when relevant |
| Order/catalog events | captured where implemented by backend services |
| Retention | controlled by backend telemetry settings |

## Event Principles

- Capture user behavior events when they support product, reliability, or operational decisions.
- Avoid raw secrets, raw Telegram `initData`, full auth payloads, bot tokens, DB URLs, JWTs, and production env values.
- Prefer structured event names and typed payloads.
- Keep payloads small enough for the configured telemetry body limit.
- Respect rate limits.

## Backend Settings

| Setting | Purpose |
| --- | --- |
| `TELEMETRY_ENABLED` | Enables telemetry ingestion |
| `TELEMETRY_MAX_EVENTS_PER_BATCH` | Maximum events accepted in one request |
| `TELEMETRY_MAX_BODY_BYTES` | Maximum telemetry body size |
| `TELEMETRY_SUCCESS_SAMPLE_RATE` | Sampling for successful operations |
| `TELEMETRY_WEB_VITAL_SAMPLE_RATE` | Sampling for web vitals |
| `TELEMETRY_ROUTE_SAMPLE_RATE` | Sampling for route events |
| `TELEMETRY_NETWORK_SAMPLE_RATE` | Sampling for network events |
| `TELEMETRY_RETENTION_DAYS` | Retention period |
| `TELEMETRY_CLEANUP_BATCH_SIZE` | Cleanup batch size |
| `RATE_LIMIT_TELEMETRY_REQUESTS` | Telemetry rate limit |
| `RATE_LIMIT_TELEMETRY_WINDOW_SECONDS` | Telemetry rate-limit window |

## Mini App Telemetry

Mini App telemetry is intended for:

- route transitions
- web vitals
- selected network diagnostics
- product/catalog interaction events
- cart and checkout funnel events where implemented

The Mini App can disable telemetry with:

```text
VITE_TELEMETRY_DISABLED=true
```

## Banner Analytics

Banner events are emitted for public banner views and clicks when the UI/backend path captures them. Banner types currently include:

- `horizontal`
- `vertical`
- `popup`
- `aggressive_popup`

Current implemented crop ratios are documented in `docs/ARCHITECTURE.md`.

## Privacy and Security

Do not store:

- raw Telegram `initData`
- bot tokens
- JWTs
- database URLs with passwords
- production env values
- payment receipt file contents in analytics payloads
- customer free-form messages unless a feature explicitly requires and sanitizes them

Telegram identifiers and user ids should be treated as personal data.

## Operations

For production telemetry issues:

```bash
cd /opt/telegram-shop
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=250 backend
```

For health checks:

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

## Checks

Backend:

```bash
cd backend
pytest
```

Mini App:

```bash
cd mini-app
npm test -- --run
npm run build
```
