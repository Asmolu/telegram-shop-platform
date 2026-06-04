# Codex Workflow

## Goal

Use GitHub as the source of truth so Codex can work against repository state, produce diffs, and help implement sprint tasks.

## Repository preparation

This repository includes `AGENTS.md` in the root. Keep it updated because Codex reads it before working and uses it as durable project guidance.

## Recommended task format for Codex

Use small, focused tasks.

Good:

```text
Implement Sprint 1 auth foundation in backend only.
Follow AGENTS.md. Add Telegram initData validation service, JWT creation, User repository methods, and tests. Do not implement frontend yet.
```

Bad:

```text
Build the whole shop.
```

## Suggested first Codex tasks

1. Validate current scaffold and fix import/config issues.
2. Create initial Alembic migration from SQLAlchemy models.
3. Implement auth module: Telegram initData validation + JWT.
4. Implement user repository/service.
5. Implement product catalog CRUD.
6. Implement upload validation and local file storage.
7. Implement cart module.
8. Implement order checkout transaction.

## Review checklist for Codex changes

Before merging Codex-generated changes, check:

- No secrets were added.
- No `.env` file was committed.
- No NestJS/Prisma backend code was added.
- New DB fields have Alembic migrations.
- Business logic is not inside routers.
- Seller Portal auth uses the protected Bot 2 webhook start-token verification
  flow, requires seller group approval before code delivery, and never exposes
  bot tokens.
- Bot 2 seller security commands are restricted to the configured seller group
  and audit critical actions.
- Customer notification changes keep Bot 1 separate from Bot 2, use
  `POST /api/v1/telegram/customer-bot/webhook` protected by
  `TELEGRAM_CUSTOMER_WEBHOOK_SECRET`, and never expose bot tokens or raw
  Telegram chat IDs in frontend responses.
- Mini App customer notification settings must use backend APIs and the
  Telegram WebApp UI boundary only; do not store or forward raw `initData`.
- Seller Panel customer notification views are registry/listing only for MVP
  Phase 1. Do not add customer campaigns, mass sending, broadcast deliveries,
  or campaign UI unless a later sprint explicitly asks for them.
- Tests or smoke checks were added for important behavior.
- README/SRS/Sprint Plan were updated if architecture changed.

## Useful prompts

```text
Read AGENTS.md, SRS.README.md, and SPRINT_PLAN.md. Summarize the current architecture and identify the next safest implementation task. Do not modify files yet.
```

```text
Implement the next task from Sprint 0 only. Keep the diff small. Run backend checks and report what passed or failed.
```

```text
Review the current diff for architecture violations against AGENTS.md. Do not modify files. Return a prioritized list of issues.
```
