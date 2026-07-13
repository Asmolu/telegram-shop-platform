# Локальная разработка

**Срез:** `325e3af`, 13 июля 2026 года. Полная инструкция — [Development](engineering/DEVELOPMENT.md); правила агента — корневой `AGENTS.md`.

## Backend

```powershell
cd C:\Project\TelegramShopPlatform\backend
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest
```

Ожидаемый head среза — `20260713_0056`. Реальные env/secrets не выводить. Business logic размещать в service, SQL — в repository; schema change сопровождается Alembic.

## Frontend

```powershell
cd C:\Project\TelegramShopPlatform\mini-app
npm test -- --run
npm run build
npm run verify:bundle

cd C:\Project\TelegramShopPlatform\seller-panel
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

Перед UI-работой прочитать `UI_DESIGN_SPEC.README.md`. Mini App остается mobile-first marketplace, Seller Panel — desktop-first dashboard. Завершать `git diff --check`; не затрагивать чужие untracked `.codex-tmp/`.
