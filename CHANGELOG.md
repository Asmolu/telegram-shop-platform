# Changelog

## Unreleased

- Simplified Seller Panel Customer Notifications by hiding template UI and manual batch sending.
- Added one optional image per customer campaign, sent by Bot 1 as Telegram `sendPhoto` with caption text.
- Made Bot 1 `/start` enable service and marketing notifications, with a migration backfill for active chats that did not explicitly opt out.
- Added automatic linking of existing Bot 1 subscriptions after Mini App Telegram auth and subscription reads.
- Added the `connected` campaign audience for all active Bot 1 chats, including unlinked subscriptions.

## 0.1.0 — Initial scaffold

- Prepared repository for GitHub and Codex workflow.
- Switched backend architecture to Python/FastAPI.
- Added SQLAlchemy/Alembic/PostgreSQL backend baseline.
- Added React/Vite/TypeScript frontend placeholders for Mini App and Seller Panel.
- Added Docker Compose local development stack.
- Added GitHub CI workflow and project documentation.
