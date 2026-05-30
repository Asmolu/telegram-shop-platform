# Security Review

Sprint 14 production hardening reviewed authentication, authorization, uploads, secrets, CORS, rate limiting, and public data exposure.

## Implemented

- Production settings reject the default `JWT_SECRET_KEY` when `APP_ENV` is `production`, `prod`, or `staging`.
- Production settings reject wildcard `CORS_ORIGINS`.
- `.gitignore` excludes `.env`, `.env.*`, secrets, logs, dumps, and uploaded user files while preserving `.env.example`.
- Upload validation continues to enforce size, extension, MIME type, safe filenames, and path containment.
- Seller/admin routes remain protected through role dependencies.
- Analytics, audit logs, notifications, uploads, promo management, review moderation, order management, and product management keep protected endpoints.
- Public endpoints expose only public catalog, taxonomy, active banners, and approved reviews.
- Rate limiting now covers Telegram login, uploads, checkout, promo validation, review creation, and a global API limit.
- Structured request logging avoids Authorization headers and does not log `.env` values or tokens.
- Redis cache failures are non-fatal for public catalog endpoints.

## Known Limitations

- Error monitoring is configured through environment placeholders only; no Sentry SDK is installed for MVP.
- Admin review listing still uses its pre-existing response shape without pagination metadata.
- The production Compose profile is a single-node MVP deployment profile, not a high-availability architecture.
- Redis-backed rate limiting falls back to in-memory limits if Redis is unavailable; this fallback is per-process.

## Pre-launch Checklist

- Replace every placeholder in `backend/.env.production`.
- Use a long random `JWT_SECRET_KEY`.
- Set explicit HTTPS origins in `CORS_ORIGINS`.
- Keep Telegram bot tokens only in backend env files.
- Run `alembic upgrade head` against staging from a clean database.
- Run backend tests and frontend builds.
- Take and restore-test a PostgreSQL backup.
- Archive and restore-test uploads.
