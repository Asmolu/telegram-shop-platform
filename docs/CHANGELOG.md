# Changelog документационного source of truth

Статус: release record. Последняя проверка: 2026-07-13. Конфиденциальность: Public.

## 2026-07-13 — cumulative production release

Deployed commit: `325e3af2a79dd9d4af92050e272169828d0edfbf`.

### Product

- Добавлен customer return UX с текущим 24-hour window, обязательным media attachment,
  partial items и support dropdown. Legal compliance не утверждена.
- Добавлены Look image badges, shared Seller Panel badge configurator и metadata default
  component selection. Текущий Mini App выбирает все components при открытии Look.
- Checkout требует `height_cm` и `weight_kg`; backend принимает legacy строки в
  `delivery_comment`, но explicit fields имеют приоритет.
- Усилены field-level validation и customer-visible errors.
- Добавлены durable PostgreSQL in-app notifications для order/payment/return transitions,
  sequential oldest-first display, acknowledgement и source-key deduplication.
- Approved payment popup переведен на photo variant с seller contacts; legacy banner
  compatibility сохранена без исторического массового backfill.

### Reliability and schema

- `20260712_0055`: Look badge fields.
- `20260713_0056`: `customer_in_app_notifications`, indexes, enums и unique source key.
- Transactional outbox migrations `20260711_0053` и fencing `20260712_0054` остаются
  обязательной базой.
- Mini App production Docker build hotfix вошел в deployed commit.

### Compatibility and rollback

Старая backend версия может игнорировать additive columns/table, но downgrade `0056` удаляет
notification history, а downgrade `0055` — Look badge configuration. Рекомендуется
no-downgrade-first: вернуть application image и сохранять additive schema, если incident это
позволяет. Перед schema rollback обязателен verified backup.

### Проверки релиза

Backend strict: 1,098 passed, 3 skipped (Windows без `fcntl` для трех Linux-only tests);
focused notification/outbox PostgreSQL: 19 passed; migrations: 48 passed; focused backend:
416 passed; Mini App: 258 passed, notification-focused 21 passed; Seller Panel: 75 passed;
оба frontend build, Mini App production Docker build и Alembic check passed. Counts — снимок.

Источник: Git commits `63b7134`…`325e3af`, `backend/tests/`, `mini-app/src/**/*.test.tsx`,
`seller-panel/tests/`, migrations `0055` и `0056`.

