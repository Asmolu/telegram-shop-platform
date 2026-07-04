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
