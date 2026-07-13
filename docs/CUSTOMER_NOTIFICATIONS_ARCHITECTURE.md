# Архитектура customer notifications

**Срез:** `325e3af`, 13 июля 2026 года. Канонические документы: [Product Notifications](product/NOTIFICATIONS.md), [Outbox](engineering/OUTBOX_ARCHITECTURE.md), [In-app Notifications](engineering/IN_APP_NOTIFICATIONS_ARCHITECTURE.md).

Bot 1 владеет customer `/start`, `/stop`, service notifications, campaigns и channel entry publish/pin. Bot 2 обслуживает seller/admin/auth и не используется для customer delivery. `/start` создает/обновляет реальное private-chat subscription state; `/stop` отключает eligibility по текущим правилам.

Mini App write access сохраняется через `POST /api/v1/customer-notifications/me/write-access`. Он позволяет service delivery и не включает marketing. Service send предпочитает реальный `telegram_chat_id`; при его отсутствии может использовать `telegram_user_id`, только если `write_access_granted=true`. Campaign требует реальный private Bot 1 chat и eligible opt-in.

PostgreSQL хранит durable state, outbox обеспечивает отправку после persistence, in-app события читаются oldest-first и получают `seen_at`. Исторический bulk backfill не выполнялся; legacy approved payment может материализоваться лениво. Raw Telegram `initData` не хранится и не логируется.
