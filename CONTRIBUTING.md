# Contributing

This repository is the StyleXac Telegram commerce platform. Contributions must preserve the current FastAPI/React architecture and production safety rules.

## Before You Start

```bash
git status --short
git fetch origin
git pull --ff-only origin main
```

Read the relevant docs:

- `README.md`
- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/LOCAL_DEVELOPMENT.md`
- `docs/TESTING.md`
- `UI_DESIGN_SPEC.README.md` for Mini App or Seller Panel UI work

## Architecture Rules

- Backend runtime is Python/FastAPI.
- Do not add NestJS, Prisma, or Node.js backend runtime.
- Keep business logic out of routers.
- Put business rules and transactions in services.
- Put SQLAlchemy queries in repositories.
- Add Alembic migrations for database schema changes.
- PostgreSQL is the source of truth.
- Redis is used for cache, rate limiting, and temporary state where implemented.

## Bot Rules

Bot 1:

- customer `/start`
- customer `/stop`
- service notifications
- customer campaigns
- channel entry publish/pin

Bot 2:

- seller/admin/auth-related flows

Do not mix these responsibilities.

## Checks

Always:

```bash
git diff --check
```

Backend:

```bash
cd backend
python -m compileall app tests
ruff check .
pytest
```

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

## Documentation

Update docs when changing:

- architecture
- commands
- environment variables
- domains
- production deployment
- backup/restore flow
- customer notifications
- channel entry
- bot responsibilities
- UI behavior
- sprint scope

## Security

Never commit or document real:

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

Use placeholders in examples: `<SECRET>`, `<BOT_TOKEN>`, `<DATABASE_URL>`, `<JWT_SECRET>`.

## Pull Requests

PR description should include:

- summary of changes
- affected areas
- migrations, if any
- docs updated, if applicable
- checks run
- checks not run and why
- production risks, if any
