# Testing and Checks

Run checks for the area changed. Documentation-only changes always require `git diff --check` and the consistency searches in this file.

## Backend

```bash
cd backend
python -m compileall app tests
ruff check .
pytest
```

Strict warning mode:

```bash
cd backend
pytest -W error
```

Focused checks for migrations, channel entry, and customer notifications:

```bash
cd backend
pytest tests/test_migrations.py tests/test_channel_entry.py tests/test_customer_notifications.py
```

If the local host does not have Python, Ruff, Pytest, or the required services, run the backend checks inside the backend Docker container. Some reverse-proxy tests read deploy/Caddy examples and may require the deploy directory mounted read-only in the container.

## Mini App

```bash
cd mini-app
npm test -- --run
npm run build
npm run verify:bundle
```

## Seller Panel

```bash
cd seller-panel
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

## Repository

```bash
git diff --check
```

## Production Smoke Checks

Use after production deploy or reverse proxy changes:

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```

## Docker Smoke Test

Use when infrastructure or compose behavior changes:

```bash
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

## Documentation Consistency Searches

Search for old current-domain references:

```bash
rg -n "tsplatform\.ru|mini\.tsplatform\.ru|api\.tsplatform\.ru|seller\.tsplatform\.ru" .
```

Search for stale migration references:

```bash
rg -n "20260628_0039" .
```

`20260628_0039` is the current documented production head. Older migration ids may appear only when clearly labeled as historical.

Search for notification and channel-entry wording when those areas change:

```bash
rg -n "write_access|write-access|requestWriteAccess|channel-entry|channel_entry|Bot 1|Bot 2" README.md docs backend mini-app seller-panel
```

## Markdown Lint

Run markdown lint only when a markdown linter is already available locally:

```bash
markdownlint README.md docs/**/*.md
```

Do not install a new markdown dependency solely for a documentation-only change.
