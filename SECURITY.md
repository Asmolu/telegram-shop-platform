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

## Sprint 14 hardening

- Production/staging startup rejects the default development `JWT_SECRET_KEY`.
- Production/staging startup rejects wildcard `CORS_ORIGINS`.
- API rate limiting is configurable and applied to login, uploads, checkout, promo validation, review creation, and global API traffic.
- Public catalog, taxonomy, banner, and approved review cache reads must fail open to PostgreSQL when Redis is unavailable.
- Structured request logs include request metadata but never Authorization headers or env values.

See `docs/SECURITY_REVIEW.md` for the current MVP security review and known limitations.
