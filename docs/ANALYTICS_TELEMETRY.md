# Privacy-Safe Telemetry

Prompt 3B1 adds Mini App performance and reliability telemetry without external
analytics services, fingerprinting, or production deployment changes.

## Architecture

- Mini App uses a lightweight in-memory telemetry client.
- The queue is not persisted to `localStorage`.
- A random `telemetry_session_id` is generated per Mini App browser session and
  stored in `sessionStorage` with a short TTL.
- Telemetry is sent to `POST /api/v1/analytics/telemetry` in bounded batches.
- The endpoint uses the existing FastAPI analytics module and stores safe rows
  in `analytics_events`.
- Backend resolves `user_id` from JWT when the telemetry request includes valid
  auth, but the frontend never sends Telegram ID or internal user ID.

## Event Schema

Current schema version is `1`.

Allowed event names:

- App lifecycle: `mini_app.bootstrap_started`,
  `mini_app.bootstrap_completed`, `telegram.initialized`, `auth.started`,
  `auth.completed`, `auth.failed`, `route.rendered`,
  `first_product_card.rendered`, `first_key_image.loaded`.
- Web Vitals: `web_vital.lcp`, `web_vital.inp`, `web_vital.cls`,
  `web_vital.ttfb`, `web_vital.fcp`.
- Network/API: `api.request_completed`, `api.request_failed`,
  `api.retry_scheduled`, `api.retry_exhausted`, `network.state_changed`.
- Critical flows: `checkout.started`, `checkout.completed`,
  `checkout.failed`, `checkout.ambiguous_outcome`,
  `payment.submit_started`, `payment.submit_completed`,
  `payment.submit_failed`, `receipt.prepare_completed`,
  `receipt.upload_completed`, `receipt.upload_failed`.
- Reliability: `chunk.load_failed`, `chunk.reload_attempted`,
  `chunk.recovery_failed`, `frontend.error_boundary_triggered`.

## Allowlist

Telemetry accepts only:

- event name and schema version;
- route without query string;
- Telegram platform and WebApp version;
- theme mode;
- network state, effective connection type, and `saveData`;
- durations and Web Vital numeric values;
- HTTP method, normalized endpoint scope, status, retry count, request ID;
- normalized error category;
- app version;
- boolean success/failure flags;
- coarse payload/response byte buckets;
- coarse viewport/device class;
- short hash of an idempotency key for ambiguous critical operations.

Endpoint scopes are normalized, for example `/products/:id`, never
`/products/123?search=text`.

## Forbidden Fields

The backend rejects unknown fields. Do not send:

- Telegram `initData` or `initDataUnsafe`;
- JWTs, Authorization headers, cookies, tokens, webhook secrets, passwords;
- full URLs with query strings;
- search query text or arbitrary user input;
- recipient names, phone, city/address, height/weight, checkout comments;
- payment recipient details;
- receipt content, path, URL, file name, or binary data;
- promo code values;
- raw user agent, raw stack trace, raw exception, request/response bodies;
- frontend-supplied `user_id`, Telegram ID, or IP.

Telemetry must not be used for IP geolocation, fraud detection, authentication,
pricing, or catalog business logic.

## Sampling

Always kept:

- auth failures;
- retry exhausted;
- checkout/payment/receipt failures;
- checkout ambiguous outcomes;
- chunk recovery failures;
- error boundary events;
- poor Web Vitals above threshold.

Sampled:

- successful API GET telemetry;
- route render events;
- ordinary Web Vitals;
- normal network transitions.

Sampling is deterministic by telemetry session and event class. Defaults live in
backend settings:

```text
TELEMETRY_SUCCESS_SAMPLE_RATE=0.2
TELEMETRY_WEB_VITAL_SAMPLE_RATE=0.5
TELEMETRY_ROUTE_SAMPLE_RATE=0.25
TELEMETRY_NETWORK_SAMPLE_RATE=0.25
```

There is no remote dynamic telemetry config.

## Ingestion Limits

Defaults:

```text
TELEMETRY_MAX_EVENTS_PER_BATCH=25
TELEMETRY_MAX_BODY_BYTES=65536
RATE_LIMIT_TELEMETRY_REQUESTS=60
RATE_LIMIT_TELEMETRY_WINDOW_SECONDS=60
```

Frontend queue defaults:

- max queue: 80 events;
- max batch: 20 events;
- max event: 4 KB;
- max payload: 32 KB;
- flush timer: 5 seconds;
- page-hide best-effort flush uses `sendBeacon` when possible.

Telemetry failures are ignored by the UI and do not use the main API retry
policy or NetworkBanner state.

Disable telemetry locally:

```text
VITE_TELEMETRY_DISABLED=true
TELEMETRY_ENABLED=false
```

## Retention

Raw telemetry retention default is 60 days. Cleanup is batch-wise and supports
dry-run through `AnalyticsService.cleanup_telemetry(...)`; production cleanup is
not run automatically by Prompt 3B1.

CLI dry-run:

```bash
cd backend
python scripts/cleanup_telemetry.py --days 60 --batch-size 500
```

Execute one batch:

```bash
cd backend
python scripts/cleanup_telemetry.py --days 60 --batch-size 500 --execute
```

Critical operational errors can be retained longer later through aggregated
reporting, but raw telemetry should stay short-lived.

## Deferred

Frankfurt deployment, same-origin API routing, Caddy production headers,
Telegram WebView validation on real devices, real VPN measurement, RUM
dashboards, and synthetic monitoring are deferred to Prompt 3B2.
