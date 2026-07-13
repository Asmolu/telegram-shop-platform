# Authentication and RBAC

## Customer

Backend parses Telegram initData, verifies HMAC with Bot token, requires hash/user/auth_date,
rejects >60s future time and data older than configured max (default 86400s), then upserts User and
issues HS256 JWT. Logs contain only error code/booleans/age/request id, never raw initData.

## Seller

Seller flow uses normalized email, password policy (8–128, letter+digit), hashed credentials,
Telegram link/approval callbacks with HMAC-derived callback data, verification expiry and JWT.
Passwords/hashes/tokens are Restricted data and never documentation content.

## Authorization

`get_current_user` verifies JWT signature/expiration, loads User and rejects inactive account.
`require_roles` enforces `USER`, `SELLER`, `ADMIN`; services perform ownership and state checks.
Webhook security uses configured secret headers/path compatibility plus Telegram identity/group checks.

JWT only supports HS256; production validator rejects default local secret and wildcard CORS.

Sources: `auth/telegram.py`, `auth/service.py`, `core/security.py`, `common/deps.py`,
`seller_auth/*`, `telegram/router.py`.

