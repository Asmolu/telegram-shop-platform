# Тестирование

**Срез evidence:** commit `325e3af`, 13 июля 2026 года. Канонические команды, уровни и правила — [Engineering Testing](engineering/TESTING.md).

Предоставленный release snapshot: backend strict — 1098 passed и 3 skipped из-за Windows `fcntl`; focused PostgreSQL outbox/in-app — 19; migrations — 48; focused backend — 416; Mini App — 258, focused notification — 21; Seller Panel — 75. Frontend builds, Mini production Docker build и Alembic check прошли. Эти результаты относятся к указанному commit и не переносятся автоматически на последующие изменения.

Минимум перед завершением определяется затронутой областью и корневым `AGENTS.md`: backend compile/Ruff/pytest и при необходимости `pytest -W error`; Mini tests/build/bundle; Seller lint/typecheck/tests/build; `git diff --check` всегда. Schema/infra требуют migration/compose smoke по риску. Production не используется как тестовая среда.
