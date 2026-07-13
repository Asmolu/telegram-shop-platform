# Компоненты

| Component | Responsibility | Persistence / dependency |
| --- | --- | --- |
| FastAPI | auth, domain services, API, workers, static uploads | PostgreSQL/Redis/files/Telegram |
| Mini App | customer UI and Telegram SDK boundary | API, browser storage/session |
| Seller Panel | seller/admin desktop UI | API |
| Bot 1 | customer/channel transport | Telegram + API services |
| Bot 2 | seller/admin/auth transport | Telegram + API services |
| PostgreSQL 16 | durable truth, locks, JSONB, enums | volume + backup |
| Redis 7 | cache/rate limiting | AOF volume; not order truth |
| Reverse proxy | TLS/domains, `/api` and `/uploads` routing | host configuration |
| Backup script | dump, uploads, metadata, checksums, restore verification | Docker, local dir, optional Yandex |

Backend modules are listed in `backend/app/api/router.py`; module pattern is router → service →
repository. Sources: `backend/app/modules/`, `backend/app/db/models.py`.

