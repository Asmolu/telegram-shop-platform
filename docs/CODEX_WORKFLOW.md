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
  flow and never exposes bot tokens.
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
