# Security Review

This document summarizes current security posture and areas that require continued attention.

## Current Production Context

| Area | Value |
| --- | --- |
| Production server | Aeza Frankfurt |
| Main domain | `https://stylexac.ru` |
| Mini App | `https://mini.stylexac.ru` |
| API | `https://api.stylexac.ru` |
| Seller Panel | `https://seller.stylexac.ru` |
| Production env | `backend/.env.production` |
| Current migration head | `20260628_0039` |

## Authentication

Implemented:

- Telegram Mini App `initData` validation server-side.
- Auth date age checks.
- Backend JWT issuance after Telegram auth.
- User upsert by Telegram user payload.
- Role model: `USER`, `SELLER`, `ADMIN`.
- Mini App login waits for `Telegram.WebApp.initData`.
- In-flight Telegram login is deduplicated.
- API `401` refresh is coordinated and retried once.
- Auth diagnostics are sanitized.

Required controls:

- Raw `initData` must not be logged or stored.
- Production JWT secret must not use the local default.
- CORS must not contain `*` in production.
- Seller/admin endpoints must require the appropriate role.

## Bot Separation

Bot 1:

- customer `/start`
- customer `/stop`
- service notifications
- customer campaigns
- channel entry publish/pin

Bot 2:

- seller/admin/auth-related flows

Risks:

- Using Bot 2 for customer sends would mix trust boundaries.
- Using Bot 1 for seller/admin auth flows would expose buyer-facing bot behavior to admin workflows.

Control: keep tokens, webhook secrets, code paths, docs, and operational checks separate.

## Secrets

Never commit or document:

- `.env`
- `backend/.env.production`
- bot tokens
- DB passwords
- JWT secrets
- Yandex Disk tokens
- private keys
- uploaded user files
- database dumps
- production credentials

Use placeholders only:

```text
<SECRET>
<BOT_TOKEN>
<DATABASE_URL>
<JWT_SECRET>
```

## Uploads

Implemented controls:

- allowed extensions and MIME validation
- image decoding validation
- size limits
- safe filenames
- path containment
- profile-specific aspect-ratio validation where configured
- file paths/URLs stored in PostgreSQL instead of file bytes

Sensitive upload class: manual payment receipts. Receipts should not be cached publicly and should not be reused in analytics payloads.

## Customer Notifications

Security-sensitive behavior:

- Write access is requested only after user action.
- Write access enables service notifications, not marketing consent.
- `/stop` disables service and marketing eligibility.
- Service delivery prefers real private-chat `telegram_chat_id`.
- Current service fallback can use `telegram_user_id` only when write access is granted.
- Campaign delivery requires real private Bot 1 chat and opt-in eligibility.
- Telegram delivery errors are sanitized.

Privacy risks:

- Telegram ids are personal data.
- Campaign reports may reveal customer eligibility and delivery status.
- Logs must not contain raw bot tokens or raw request payloads with secrets.

## Channel Entry

Implemented:

- Seller Panel route `/channel-entry`.
- Bot 1 publishes and optionally pins a channel message.
- Channel button is a URL button to Mini App `startapp`.
- History stores Telegram `message_id` and pin status.

Important security point: channel-entry auth can create/update a `User`, but it does not create real private Bot 1 chat state. Notification eligibility must come from write access or Bot 1 `/start`.

## Production Infrastructure

Controls:

- TLS terminated by host Caddy.
- HTTP/3/QUIC intentionally disabled.
- `tsplatform-mss-clamp.service` intentionally enabled for ports `80` and `443`.
- Production compose uses `backend/.env.production`.
- PostgreSQL and Redis are internal Docker services.

Operational checks:

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
sudo systemctl status tsplatform-mss-clamp.service --no-pager
```

## Required Review Before High-Risk Changes

Review security impact when changing:

- auth/session logic
- Telegram `initData` validation
- bot token ownership
- webhook secrets
- customer notification target resolution
- campaign eligibility
- checkout transactions
- order status notifications
- upload validation
- public URL generation
- CORS
- production reverse proxy
- Alembic migrations that touch customer/order/subscription data

## Current Residual Risks

- Campaign delivery and service notification behavior depend on Telegram API availability and rate limits.
- Local filesystem uploads require reliable volume backup and restore.
- Seller/admin role assignment must be controlled operationally.
- Any direct database repair can bypass service-level audit rules and must be backed up and documented.
