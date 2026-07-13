# Engineering testing

Backend suites cover unit/service/API, PostgreSQL migrations/concurrency, outbox, notifications,
checkout and workers. Frontends use Vitest/jsdom (Mini App) and Node tests plus TypeScript (Seller).

Commands are canonical in [../TESTING.md](../TESTING.md). Release snapshot 2026-07-13: backend
strict 1,098 passed/3 skipped; focused PG notification/outbox 19; migration 48; focused backend 416;
Mini App 258 plus notification-focused 21; Seller Panel 75; builds/Docker build/Alembic check passed.
Three skips are Linux `fcntl` locking tests unavailable on Windows. Counts may change.

