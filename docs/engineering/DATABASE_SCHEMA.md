# Database schema

Current head: `20260713_0056`. Linear chain: 56 revisions from `20260527_0001` to `20260713_0056`.
PostgreSQL-specific features: native enums, JSONB variant, `pg_trgm`, row locks,
`FOR UPDATE SKIP LOCKED`, sequences/indexes and `ON CONFLICT`.

| Table/model | Purpose / relationships | Constraints, deletion, PII |
| --- | --- | --- |
| `users` / User | identity, role, Telegram/profile/personal data | Telegram identity; PII; parent for owned data |
| `user_blocks` | active/historical blocks by user/Telegram | actor refs SET NULL; indexed active targets |
| `seller_credentials` | password credential for User | user CASCADE; sensitive hash |
| `pending_seller_registrations` | approval/verification state | email/Telegram/password-related sensitive metadata |
| `idempotency_records` | request hash/response replay | unique user/scope/key; expiry index; user CASCADE |
| `customer_telegram_subscriptions` | Bot 1 chat/opt-ins/write access | unique user and Telegram; PII/chat identifiers |
| `telegram_channels` | configured publish targets | unique chat id; actor SET NULL |
| `telegram_channel_entry_messages` | publish/pin history | channel SET NULL; sanitized errors |
| `categories`, `tags` | taxonomy and media paths | unique slug conventions; no customer PII |
| `products` | sellable catalog, visibility/search/badges | status enums, JSON/fields, legacy category SET NULL |
| `product_categories` | up to three prioritized assignments | unique product/category and product/priority; CASCADE |
| `product_tags` | many-to-many tag link | composite PK; CASCADE |
| `product_related_products` | configured relation | unique directed relation; CASCADE |
| `product_variants` | SKU/size/color/stock/reserved | product CASCADE; stock indexes/checks |
| `product_images` | local file/derivative paths | product CASCADE |
| `route_aliases` | old slug → entity | type/id/alias indexes; creator SET NULL |
| `carts`, `cart_items` | owned mutable selection | user/item CASCADE; product/variant CASCADE; Look SET NULL |
| `orders` | totals, delivery/customer snapshots/status | user CASCADE; promo SET NULL; PII |
| `order_items` | immutable purchased product snapshots | order CASCADE; product/variant RESTRICT; Look SET NULL |
| `seller_payment_settings` | manual payment display/requisites | sensitive operational data; updater SET NULL |
| `manual_payments` | one payment/order, evidence/status | unique order; order CASCADE; actor SET NULL; PII/evidence |
| `promo_codes` | discount/rules/windows | unique normalized code expected |
| `coupon_usages` | redemption timing/snapshot link | unique promo/order; user CASCADE; order SET NULL |
| `return_requests` | one request/order | unique order; order/user CASCADE; actor SET NULL; PII |
| `return_request_items` | returned snapshots/restock audit | unique request/order item; refs mixed CASCADE/SET NULL |
| `return_request_attachments` | local sensitive media paths | request CASCADE; PII/content risk |
| `return_refunds` | one manual refund record | unique request; actor SET NULL |
| `reviews` | purchase-linked moderated content | unique user/product; order SET NULL |
| `favorites` | owned saved products | unique user/product; both CASCADE |
| `looks`, `look_items`, `look_images` | outfit composition/media | unique Look/product; product RESTRICT; image paths |
| `banners` | display/destination/media | enum target/display; analytics side effects |
| `notifications` | seller/internal delivery history | unique idempotency tuple; actor SET NULL |
| `customer_service_notification_deliveries` | service-send outcome | user CASCADE, order/subscription SET NULL |
| `notification_templates` | reusable message content | creator/updater SET NULL |
| `broadcast_campaigns` | campaign state/message/audience JSONB | template SET NULL; creator RESTRICT; PII-light content |
| `broadcast_deliveries` | per-recipient delivery state | campaign CASCADE; subscription RESTRICT; chat PII |
| `outbox_events` | durable immutable event payload JSONB | unique UUID; poll/lock indexes |
| `outbox_deliveries` | per-consumer state | unique event/consumer; event CASCADE |
| `customer_in_app_notifications` | customer durable popup queue | unique source key; user CASCADE; domain refs SET NULL |
| `analytics_events` | privacy-safe telemetry JSONB | session/request/event indexes; user SET NULL |
| `audit_logs` | critical action snapshots JSONB | actor SET NULL; may contain business/PII snapshots |

Transactions: checkout and status mutation create domain/outbox/in-app rows in one transaction;
external sends follow commit. Archival is entity-specific (`ARCHIVED`, inactive flags); no universal
data-retention/archive subsystem exists.

Sources: `backend/app/db/models.py`, all `backend/alembic/versions/*.py`, repositories/services.

