# GitHub Setup

This document covers repository setup and GitHub workflow. It does not contain production secrets.

## Repository

Project: StyleXac / TelegramShopPlatform.

Primary branch convention:

```text
main
```

Recommended feature branch prefix for Codex-created branches:

```text
codex/
```

## First Push From a New Local Clone

```bash
git remote -v
git status --short
git branch --show-current
git fetch origin
git pull --ff-only origin main
```

If the repository is not connected to GitHub yet:

```bash
git remote add origin <REPOSITORY_URL>
git push -u origin main
```

Do not paste private repository URLs into public docs if they include credentials.

## Commit Style

Use concise imperative commit messages:

- `Initialize FastAPI backend scaffold`
- `Add product catalog models`
- `Implement cart service`
- `Add order checkout transaction`
- `Configure GitHub CI`

For current feature work, keep the subject focused on the changed behavior:

- `Document Bot 1 write access flow`
- `Update production deployment runbook`
- `Fix channel entry history status`

## Pull Request Checklist

Before opening or merging a PR:

- `git diff --check`
- backend checks if backend changed
- Mini App checks if Mini App changed
- Seller Panel checks if Seller Panel changed
- documentation updated when architecture, commands, environment variables, production operations, or sprint scope changed
- no secrets or uploaded user files included
- no raw production env values included

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

## Secret Review

Before pushing:

```bash
git status --short
git diff --check
git diff --cached --name-only
```

Never push:

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
