# Security Policy

This project handles customer data, Telegram identities, seller/admin access, uploads, orders, and production infrastructure. Treat secrets and operational data carefully.

## Supported Production Surface

| Surface | Domain |
| --- | --- |
| Main domain and Mini App entry | `https://stylexac.ru` |
| Mini App | `https://mini.stylexac.ru` |
| API | `https://api.stylexac.ru` |
| Seller Panel | `https://seller.stylexac.ru` |

Production server: Aeza Frankfurt. Production path: `/opt/telegram-shop`.

## Reporting a Vulnerability

Report security issues privately to the project maintainer. Do not open a public issue containing exploit details, real secrets, customer data, bot tokens, database credentials, JWTs, private keys, or production env values.

Include:

- affected component
- impact
- reproduction steps without real secrets
- suspected commit or release window
- logs with secrets removed
- whether customer data or order data may be affected

## Secret Handling

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

Use placeholders:

```text
<SECRET>
<BOT_TOKEN>
<DATABASE_URL>
<JWT_SECRET>
```

## Authentication Requirements

- Telegram Mini App `initData` must be validated server-side.
- Raw `initData` must not be logged or stored.
- JWT secret must be strong in production.
- CORS must not use `*` in production.
- Seller/admin endpoints must enforce roles.
- Auth diagnostics must be sanitized.

## Bot Separation

Bot 1 handles customer flows:

- `/start`
- `/stop`
- service notifications
- campaigns
- channel entry publish/pin

Bot 2 handles seller/admin/auth-related flows.

Do not use Bot 2 for customer/channel buyer notification flows.

## Upload Security

Uploads must keep:

- size validation
- extension validation
- MIME validation
- image decoding validation
- safe filenames
- path containment
- profile-specific aspect ratio validation where implemented

PostgreSQL stores paths/URLs only, not file bytes.

## Production Operations

Before migrations:

```bash
ssh tsplatform-frankfurt
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
```

Smoke checks:

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

Do not paste production logs publicly if they contain customer data, Telegram ids, stack traces with request metadata, or env values.
