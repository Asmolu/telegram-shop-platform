# Security Policy

## Secrets

Never commit:

- `.env` files
- Telegram bot tokens
- JWT secrets
- database credentials
- private keys
- production dumps
- uploaded user files

Use `.env.example` files for placeholders only.

## Authentication

The planned authentication model is:

- Telegram Mini App `initData` validation for Telegram users
- JWT for API session authorization
- RBAC for USER / SELLER / ADMIN access separation

## Reporting security issues

Create a private issue or contact the repository owner directly. Do not disclose exploitable vulnerabilities publicly before a fix exists.

## High-risk areas

- Telegram `initData` validation
- JWT signing and expiration
- upload path handling
- order checkout transaction
- stock deduction race conditions
- promo code abuse / replay
- seller/admin RBAC boundaries
- analytics/telemetry payload allowlists

## Sprint 14 hardening

- Production/staging startup rejects the default development `JWT_SECRET_KEY`.
- Production/staging startup rejects wildcard `CORS_ORIGINS`.
- API rate limiting is configurable and applied to login, uploads, checkout, promo validation, review creation, and global API traffic.
- Public catalog, taxonomy, banner, and approved review cache reads must fail open to PostgreSQL when Redis is unavailable.
- Structured request logs include request metadata but never Authorization headers or env values.

## Telemetry privacy

Mini App telemetry must stay privacy-safe. The ingestion endpoint rejects
unknown fields and must not accept Telegram `initData`, JWTs, cookies,
Authorization headers, full URLs with query strings, search text, checkout
personal data, payment recipient details, receipt paths/content, raw stack
traces, raw user agents, or frontend-supplied user identifiers. Telemetry
session IDs are random, short-lived, and not derived from IP, user agent,
Telegram ID, or device properties. Telemetry must not be used for IP
geolocation, fraud detection, authentication, pricing, or catalog business
logic.

See `docs/SECURITY_REVIEW.md` for the current MVP security review and known limitations.
