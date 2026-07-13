# Contributing

1. Read `AGENTS.md` and UI spec when changing frontend.
2. Keep routers/services/repositories boundaries and async SQLAlchemy.
3. Add Alembic migration for schema changes; never edit deployed migration history casually.
4. Add/update tests and canonical docs; do not duplicate business rules.
5. Run relevant checks plus `git diff --check`.
6. Inspect staged diff for secrets, PII, uploads and dumps.
7. Use focused commits/PR description with migration and rollback notes.

Never combine Bot 1/Bot 2 responsibilities or introduce Node/NestJS/Prisma backend.

