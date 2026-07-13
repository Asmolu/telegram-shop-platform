# Customer Notifications Architecture

Customer notifications are implemented through Bot 1, backend subscription state, Mini App write access, and campaign delivery records.

This document describes the current production behavior after the Bot 1 write-access flow for order notifications.

## Scope

Customer notification features include:

- customer Bot 1 `/start`
- customer Bot 1 `/stop`
- service notification eligibility
- Mini App write-access persistence
- checkout/order status service notifications
- customer campaigns with images, previews, test sends, and delivery reports
- Seller Panel customer notification management

Bot 2 is not used for customer/channel buyer notification flows.

## Data Model

`CustomerTelegramSubscription` stores Bot 1 customer notification state.

| Field | Meaning |
| --- | --- |
| `user_id` | Optional backend user link |
| `telegram_user_id` | Telegram user id |
| `telegram_chat_id` | Private Bot 1 chat id when a real private chat exists |
| `chat_type` | Telegram chat type, expected `private` for customer sends |
| `has_chat` | Whether a usable private Bot 1 chat is currently known |
| `service_opt_in` | Eligibility for service notifications |
| `marketing_opt_in` | Eligibility for marketing campaigns |
| `opt_in_source` | Source of latest opt-in state |
| `blocked_at` | Timestamp when Telegram delivery showed the bot was blocked |
| `write_access_granted` | Whether Mini App write access was granted |
| `write_access_granted_at` | Grant timestamp |
| `write_access_denied_at` | Denial timestamp |
| `write_access_source` | Source of write-access result, for example Mini App profile or checkout |
| `last_start_at` | Last Bot 1 `/start` timestamp |
| `last_stop_at` | Last Bot 1 `/stop` timestamp |
| `last_delivery_error` | Sanitized last delivery error |

Campaign tables store templates, campaigns, delivery rows, attempts, status, report counters, and optional campaign image paths.

## Bot 1 `/start`

When a customer sends `/start` to Bot 1 in a private chat, the backend:

1. creates or updates `CustomerTelegramSubscription`
2. records `telegram_user_id`, `telegram_chat_id`, `chat_type=private`, and `has_chat=true`
3. clears blocked state
4. enables `service_opt_in`
5. enables `marketing_opt_in`
6. records opt-in source and timestamps
7. sends the current welcome/settings response

This path creates real private-chat state and is the strongest notification eligibility path.

## Bot 1 `/stop`

When a customer sends `/stop` to Bot 1 in a private chat, the backend:

1. updates the matching subscription
2. sets `service_opt_in=false`
3. sets `marketing_opt_in=false`
4. records opt-out timestamps
5. sends the current stop response

After `/stop`, service sends and campaigns must treat the customer as ineligible until the user opts in again.

## Mini App Write Access

The Mini App can request Telegram write access only after a user action. Current UI entry points include profile and checkout notification availability flows.

The browser flow:

1. User taps the notification action.
2. Mini App calls `Telegram.WebApp.requestWriteAccess()`.
3. Mini App posts the result to `POST /api/v1/customer-notifications/me/write-access`.
4. Backend creates or updates `CustomerTelegramSubscription` linked to the authenticated `User`.

Grant behavior:

- sets `write_access_granted=true`
- sets `write_access_granted_at`
- clears `write_access_denied_at`
- records `write_access_source`
- sets `service_opt_in=true`
- does not enable `marketing_opt_in`

Denial behavior:

- sets `write_access_granted=false`
- sets `write_access_denied_at`
- records `write_access_source`
- disables `service_opt_in` only when no active private Bot 1 chat exists
- does not change `marketing_opt_in` to true

Write access is a service-notification path. It is not marketing consent.

## Service Notification Target Resolution

Service notifications are used for order and order-status events.

Target resolution order:

1. If a subscription has a real active private Bot 1 chat, send to `telegram_chat_id`.
2. If no private chat exists and `write_access_granted=true`, current backend logic can send to `telegram_user_id`.
3. If neither target exists, record a skipped delivery.

A real active private chat means:

- `has_chat=true`
- `telegram_chat_id` is present
- `chat_type=private`
- `blocked_at` is empty

The sender records delivery status. Telegram failures are sanitized before persistence and logging.

## Delivery Failure Behavior

| Failure | Current behavior |
| --- | --- |
| No subscription | delivery skipped |
| Service opt-out | delivery skipped |
| No send target | delivery skipped |
| Telegram `403` blocked | marks subscription blocked and clears active-chat eligibility |
| Telegram rate limit | records rate-limited delivery state |
| Other Telegram/API error | records sanitized failure details |

Raw bot tokens, raw request payloads, and raw `initData` must not be logged.

## Campaigns

Customer campaigns are managed through backend campaign endpoints and Seller Panel customer notification screens.

Implemented capabilities:

- template storage in backend tables
- campaign creation and editing
- campaign image upload and removal
- preview
- test send
- scheduling/start/pause/cancel
- batch processing
- delivery rows
- delivery summary/reporting

Campaign delivery eligibility is stricter than service-notification write access. Current campaign materialization requires:

- real private Bot 1 chat
- `has_chat=true`
- `telegram_chat_id` present
- `chat_type=private`
- `blocked_at` empty
- required `service_opt_in` or `marketing_opt_in` according to campaign type

Write access alone does not make a user eligible for campaign delivery.

Supported campaign scopes include:

- all eligible customers
- connected customers
- purchasers
- product purchasers
- category purchasers
- promo-code users

Campaign images are sent as Telegram photos with captions when present. Text-only campaigns are sent as Telegram messages. Current campaign text is plain text.

## Seller Panel Behavior

Seller Panel supports customer notification operations, campaign work, delivery status, and reporting. Template tables and backend endpoints exist. The current Seller Panel UI is simplified and does not expose every backend template-management capability as a full template editor.

Profile and checkout notification availability in the Mini App should present write access as a service-notification permission, not as marketing subscription.

## Checkout and Order Notifications

Order creation and order status updates emit notifications only after successful database persistence. This protects against notifying customers about orders that did not commit.

Current service notifications can use:

- real Bot 1 private chat id
- Telegram user id when Mini App write access was granted and no private chat id exists

Delivery state is recorded for observability and retry/debug decisions.

## Durable Mini App Status Notifications

Customer order, manual-payment, and return status popups are persisted in
`customer_in_app_notifications`. They are an in-app channel and do not depend on Bot 1 chat
state, Telegram write access, service opt-in, or marketing opt-in. Their delivery does not use the
transactional outbox, although order-transition deduplication reuses its persisted occurrence ID.
The status change and its immutable title, message, payload, occurrence time, and durable source
key are written in the same database transaction. Notification insertion uses PostgreSQL
`INSERT ... ON CONFLICT DO NOTHING` targeted only at
`uq_customer_in_app_notifications_source_key`; it does not catch unrelated integrity failures or
roll back the shared service transaction.

The enforced transition graphs are:

- order: seller/admin correction may move between any of `NEW`, `PROCESSING`, `SHIPPED`,
  `DELIVERED`, and `CANCELLED`, except that an order with a `PENDING` or `SUBMITTED` manual
  payment must use the payment decision flow; a no-op status request is idempotent;
- manual payment: `PENDING -> SUBMITTED`, and `PENDING|SUBMITTED -> APPROVED|REJECTED|EXPIRED`;
  repeated requests for the current state are idempotent where exposed, terminal states cannot
  leave, and `CANCELLED` currently has no mutation path;
- return: `PENDING -> APPROVED|REJECTED|CANCELLED` and
  `APPROVED -> COMPLETED|CANCELLED`; terminal states cannot leave.

Orders therefore can re-enter a previously used status. Their source key includes the UUID of the
persisted `order.status_changed` outbox occurrence. A linked order transition caused by a manual
payment uses the persisted payment transition identity. Retries and concurrent duplicates are
fenced by the aggregate row lock and do not create another occurrence, while a later genuine
order re-entry receives a new persisted outbox identity and a new notification. Payment and return
states cannot re-enter, so their entity/status source keys remain stable. A rollback removes the
status, outbox/audit occurrence, and notification together and never reserves a source key.

The authenticated Mini App API returns the current user's unseen rows oldest-first and marks one
owned row seen idempotently. The global Mini App controller refreshes at startup, navigation,
focus, visible-state restoration, and a restrained visible-only poll; it displays and acknowledges
one item at a time. PostgreSQL `seen_at` is authoritative. Local storage is read only to reconcile
legacy approved-payment banners that a previous client dismissed before its server acknowledgement
succeeded.

Approved manual payments use the configured image snapshot and the larger payment layout. Every
other supported status uses the standard layout. The legacy payment-success endpoints remain during
rolling deployment: acknowledging through either API marks both the legacy order field and the new
notification when it exists. When a previously approved, server-unseen legacy banner has no durable
row, the new pending endpoint atomically materializes only that pending legacy candidate with the
same stable payment source key. Concurrent pending requests can create at most one row. Already-seen
approvals are excluded, future approvals create their row directly, and the Mini App registers only
the unified controller.

## Channel Entry Interaction

Channel entry users may authenticate in the Mini App through `initData`, which creates or updates a backend `User`. That does not create a real private Bot 1 chat.

For those users, service notification eligibility depends on:

- Mini App write access grant, or
- later Bot 1 `/start` in a private chat

Campaign eligibility still requires real private Bot 1 chat state.

## Security and Privacy

- Bot 1 token must be stored only as a secret value.
- Bot 2 token must not be used for customer sends.
- Raw Telegram `initData` must not be logged or stored.
- Delivery errors must be sanitized.
- Customer identifiers should be treated as personal data in logs and exports.
- Marketing consent must not be inferred from write access.

## Operational Verification

Backend focused tests:

```bash
cd backend
pytest tests/test_customer_notifications.py
```

Deploy log checks:

```bash
cd /opt/telegram-shop
docker compose --env-file backend/.env.production -f docker-compose.prod.yml logs --tail=250 backend
```

Smoke surfaces:

```bash
curl -sS -D - https://api.stylexac.ru/health -o /dev/null
curl -I https://mini.stylexac.ru/
curl -I https://seller.stylexac.ru/
```
