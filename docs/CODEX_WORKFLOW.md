# Workflow для Codex и coding agents

**Контекст:** TelegramShopPlatform / ICON STORE, commit-срез `325e3af`, Alembic `20260713_0056`. Авторитетные инструкции находятся в корневом `AGENTS.md`; этот файл — краткая памятка.

1. Проверить root/branch/status/HEAD и не трогать чужие изменения или `.codex-tmp/`.
2. Прочитать документы затронутой области; для Mini/Seller UI обязательно `UI_DESIGN_SPEC.README.md`.
3. Сверять утверждения с кодом, tests, migrations, compose и examples; не читать реальные env и не обращаться к production без явного поручения.
4. Сохранять архитектуру `router → service → repository`, async SQLAlchemy и Python backend; schema changes сопровождаются Alembic.
5. Не смешивать Bot 1 customer и Bot 2 seller/admin/auth.
6. Использовать `apply_patch` для ручных edits, сохранять unrelated worktree changes.
7. Выполнить проверки из `AGENTS.md` пропорционально области и `git diff --check`.
8. Обновить каноническую документацию, compatibility path и changelog при изменении правил/env/ops.
9. Не commit/push/deploy без явного запроса; никогда не раскрывать secrets/PII.

Production path — `/opt/telegram-shop`, домены — family `stylexac.ru`. Release truth — [Production State](PRODUCTION_STATE.md).
