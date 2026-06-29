# Codex Workflow

This repository can be edited by Codex or another AI coding agent, but changes must follow the same engineering and security rules as human changes.

## Current Context

| Area | Current value |
| --- | --- |
| Product | StyleXac / TelegramShopPlatform |
| Production domains | `stylexac.ru`, `mini.stylexac.ru`, `api.stylexac.ru`, `seller.stylexac.ru` |
| Production server | Aeza Frankfurt |
| Production path | `/opt/telegram-shop` |
| Current migration head | `20260628_0039` |

## Before Editing

1. Inspect repository structure.
2. Read relevant docs.
3. Read the implementation before changing it.
4. Check `git status --short`.
5. Identify whether the task is backend, Mini App, Seller Panel, docs, operations, or cross-cutting.
6. Keep changes scoped to the requested area.

For Mini App or Seller Panel UI work, read `UI_DESIGN_SPEC.README.md`.

## Documentation-Only Tasks

Allowed:

- edit Markdown documentation
- update examples that do not change runtime behavior
- run searches and docs checks

Not allowed:

- source code changes
- backend logic changes
- frontend logic changes
- database model changes
- Alembic migration changes
- Docker Compose behavior changes
- real secret disclosure

Always run:

```bash
git diff --check
```

Run markdown lint only if already available locally.

## Backend Tasks

Follow the module structure:

```text
backend/app/modules/<feature>/
├── router.py
├── schemas.py
├── service.py
└── repository.py
```

Rules:

- Routers stay thin.
- Services own business logic and transactions.
- Repositories own SQLAlchemy queries.
- SQLAlchemy models live in `backend/app/db/models.py` until intentionally split.
- Add Alembic migrations for schema changes.
- Use async SQLAlchemy sessions.

Relevant checks:

```bash
cd backend
python -m compileall app tests
ruff check .
pytest
```

## Frontend Tasks

Mini App:

```bash
cd mini-app
npm test -- --run
npm run build
npm run verify:bundle
```

Seller Panel:

```bash
cd seller-panel
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

Do not hardcode production API URLs. Use `VITE_API_BASE_URL` or compose build args.

## Bot and Telegram Rules

Bot 1:

- customer `/start`
- customer `/stop`
- service notifications
- customer campaigns
- channel entry publish/pin

Bot 2:

- seller/admin/auth-related flows

Telegram Mini App `initData` must always be validated server-side. Raw `initData` must not be logged or stored.

## Customer Notification Rules

- Write access is requested only after a user action.
- Write access enables service notifications only.
- Write access does not silently enable marketing campaigns.
- Service notifications prefer real private-chat `telegram_chat_id`.
- Current service notification fallback can use `telegram_user_id` when write access is granted.
- Campaign delivery requires real Bot 1 private-chat state.
- Delivery failures must be sanitized.

## Channel Entry Rules

- Seller Panel route is `/channel-entry`.
- Bot 1 publishes and pins channel messages.
- Channel button uses a URL to Mini App `startapp`.
- Do not use Telegram `web_app` button for channel posts.
- Channel-entry auth does not create real private Bot 1 chat state.

## Secrets

Never commit or document real:

- bot tokens
- DB passwords
- JWT secrets
- Yandex Disk tokens
- private keys
- production `.env` content
- uploaded user files
- database dumps

Use placeholders: `<SECRET>`, `<BOT_TOKEN>`, `<DATABASE_URL>`, `<JWT_SECRET>`.

## Final Response Checklist

When work is complete, report:

- what changed
- files changed
- checks run and results
- checks not run and why
- safety notes for secrets, migrations, and source-code scope
