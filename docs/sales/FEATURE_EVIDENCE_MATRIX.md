# Матрица функций и доказательств

**Срез:** `325e3af`, 13 июля 2026 года. Статус `Partial` означает работающую основу с явно описанным разрывом.

| Возможность | Статус | Доказательство в репозитории | Ограничение |
| --- | --- | --- | --- |
| Telegram Mini App auth | Implemented | auth service/tests, server-side HMAC | Production token/clock не проверялись |
| Каталог, категории, бренды, поиск | Implemented | product/search modules и frontend | Search scale требует нагрузочной проверки |
| Скрытые активные товары | Implemented | public list filters + direct detail | Direct URL доступен; это не security boundary |
| Looks | Partial | looks backend/Mini UI/tests | Все компоненты фактически selected по умолчанию |
| Варианты и `ONE_SIZE` | Implemented | products/cart/checkout | Accessories-only семантика не enforced |
| Transactional checkout/stock | Implemented | orders service/repository/tests | Нужен concurrency load test |
| Coupon accounting | Implemented | coupon usage и checkout | Discount применяется к goods, не delivery |
| Delivery methods/prices | Implemented | delivery enum/helper/checkout | Адрес schema требует для всех методов, включая pickup |
| Manual SBP lifecycle | Implemented | payments service/tests | Нет автоматического acquiring/webhook |
| Fulfillment statuses | Partial | orders API/UI | Нелинейные/re-entry переходы разрешены |
| Returns/refunds | Partial | returns/refunds modules/tests | 24h policy требует legal review; refund ручной |
| Reviews/favorites | Implemented | modules/UI/tests | Reviews после покупки и с модерацией |
| Bot 1 notifications/campaigns | Implemented | customer notifications/outbox/workers | Campaign нужен реальный private chat и opt-in |
| In-app notifications | Implemented | durable DB notifications/tests | Нет исторического bulk backfill |
| Channel entry | Implemented | module/docs/tests | Публикация/pin — внешнее действие Bot 1 |
| Seller RBAC/audit | Implemented | auth/scoped services/AuditLog | Нужен независимый IDOR audit |
| Analytics events | Implemented | AnalyticsEvent paths | Полнота продуктовых событий требует governance |
| Backup/restore automation | Partial | scripts/systemd/tests/docs | Unit template содержит устаревший path; prod drill не выполнялся в этой работе |
| Production deployment | Documented | compose/Caddy/Alembic/runbooks | Фактическое production состояние не проверялось |

