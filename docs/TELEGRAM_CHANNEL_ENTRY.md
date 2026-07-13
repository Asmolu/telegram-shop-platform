# Вход из Telegram-канала

**Срез:** `325e3af`, 13 июля 2026 года. Seller Panel route — `/channel-entry`, default start parameter — `channel_pin`, backend module — `backend/app/modules/channel_entry`.

Bot 1 публикует и при запросе закрепляет channel message. Bot 2 в этом customer flow не участвует. Кнопка должна быть обычной URL-ссылкой на Telegram Mini App `startapp`, а не `web_app` button. URL строится из настроенных bot username/Mini App short name; конкретное production имя не hardcode в документации.

Channel-entry `initData` проверяется backend. Поток может создать или обновить `User`, но не создает реальный private Bot 1 chat subscription. Поэтому service notification после channel entry требует отдельного private `/start` либо предоставленного write access; campaign все равно требует real private chat и eligible marketing opt-in.

Публикация и pin — внешние необратимые для аудитории действия: preview, destination channel, text, button URL и права Bot 1 проверяются перед подтверждением. Операционный порядок — [Telegram Operations](operations/TELEGRAM_OPERATIONS.md), notification rules — [Notifications](product/NOTIFICATIONS.md).
