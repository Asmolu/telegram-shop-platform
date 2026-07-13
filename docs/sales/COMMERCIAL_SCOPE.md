# Коммерческий scope

## Базовый объем

Базовый продукт включает текущий Mini App, Seller Panel, FastAPI API, PostgreSQL/Redis, два Telegram-бота, каталог/Looks, cart/checkout/orders, ручную СБП, delivery rules, returns/reviews, notifications, channel entry, контейнеризацию, миграции и документацию. Конкретная поставка фиксируется commit/release и acceptance checklist.

## Обычно отдельная услуга

Branding и контент, импорт каталога, production setup, Telegram/domain configuration, обучение продавца, юридические тексты, monitoring/on-call, backup drill, migration from legacy, SLA и послерелизная поддержка оцениваются отдельно, если договором не включены явно.

## Вне текущего продукта

- автоматический банковский acquiring, webhook reconciliation и payouts;
- встроенная ККТ/фискализация и налоговая отчетность;
- полноценный multi-vendor settlement/marketplace ledger;
- ERP/WMS/CRM/курьерские интеграции без отдельной разработки;
- мобильные native apps;
- формальная security/compliance сертификация;
- гарантированная HA/DR георезервированная инфраструктура;
- юридическое заключение.

Change request обязан содержать цели, UX/API/data изменения, migration/rollback, security/legal impact, тестирование, сроки и цену. Устное обещание не расширяет scope.

