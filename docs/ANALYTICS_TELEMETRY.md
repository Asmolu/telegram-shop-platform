# Analytics и telemetry

**Срез:** `325e3af`, 13 июля 2026 года. Backend использует `AnalyticsEvent` и модуль `backend/app/modules/analytics`; Mini App содержит telemetry client. События добавляются только там, где поддерживают продуктовые, reliability или audit решения.

Запрещено отправлять raw Telegram `initData`, tokens, passwords, payment secrets, полный адрес/телефон, содержимое вложений и неограниченные request bodies. Event schema должна иметь назначение, владельца, минимальный payload, стабильное имя, retention и способ исключения/удаления при применимом запросе субъекта.

Client telemetry не является source of truth для заказа, оплаты, stock или доступа: авторитетны PostgreSQL и backend audit/domain records. Ошибка telemetry не должна ломать checkout. Privacy/legal review должен подтвердить основания, notice/consent, processors, трансграничность и сроки. Env names и defaults приведены в [Configuration](engineering/CONFIGURATION.md), карта ПД — [Personal Data Processing Map](legal/PERSONAL_DATA_PROCESSING_MAP.md).
