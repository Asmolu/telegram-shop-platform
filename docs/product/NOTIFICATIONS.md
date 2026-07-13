# Notification architecture and customer matrix

Статус: канонический. Telegram customer, Telegram seller, campaigns, backup и Mini App in-app rows
are independent channels.

## Durable in-app matrix

| Domain | State | Popup | Actions |
| --- | --- | --- | --- |
| Order | initial `NEW` | none | — |
| Order | `PROCESSING`, `SHIPPED`, `DELIVERED` | standard | Continue |
| Order | `CANCELLED` | standard | Continue + seller contacts |
| Payment | initial `PENDING` | none | — |
| Payment | `SUBMITTED` | standard | Continue |
| Payment | `APPROVED` | photo variant | Continue + seller contacts |
| Payment | `REJECTED`, `EXPIRED`, `CANCELLED` | standard | Continue + seller contacts |
| Return | initial `PENDING` | none | — |
| Return | `APPROVED`, `REJECTED`, `COMPLETED`, `CANCELLED` | standard | Continue + seller contacts |

Rows live in PostgreSQL, are fetched oldest-first, shown sequentially and acknowledged with `seen_at`.
Mini App refreshes on polling, route change, focus and visibility. Active popup is not dismissed by
backdrop or Escape; explicit action is required. Failed acknowledgement keeps retryable server state.
Source-key unique conflict suppresses only the same transition identity; unrelated integrity errors
abort the business transaction. Order status re-entry uses outbox occurrence identity and can produce
a new notification; payment/return source key is state-based and suppresses repeated same state.

Legacy approved-payment banner: pending endpoint remains; if a legacy unseen approved order has no
durable row, one row can be created lazily. No historical bulk backfill occurred.

Source: `customer_in_app_notifications/service.py`, `repository.py`, migration `0056`,
Mini App `CustomerStatusNotificationController` and tests.

## Bot 1 subscriptions

- `/start`: upserts real private `telegram_chat_id`, `has_chat`, service eligibility.
- `/stop`: disables current notification eligibility and opt-ins per service behavior.
- Write access is requested only after user action and persisted by
  `POST /api/v1/customer-notifications/me/write-access`.
- Write access enables service notifications, never silent marketing opt-in.
- Service target prefers real private chat; may use `telegram_user_id` when write access granted.
- Campaign requires real, unblocked Bot 1 private chat plus matching service/marketing opt-in.
- Channel-entry initData can upsert User but does not establish private chat.

## Seller, campaign, backup

Bot 2 handles seller/order/payment/return callbacks and must not take Bot 1 duties. Campaigns persist
delivery rows with retry/rate-limit/blocked states. Backup script sends a status report to dedicated
backup chat (legacy seller chat fallback) when enabled; remote status may be skipped/failed.

Transactional order/payment sends are at-least-once via outbox; Telegram cannot provide exactly-once
across send/ack crash window.

