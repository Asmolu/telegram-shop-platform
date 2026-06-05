# Customer Notifications Architecture

## Goals

- Design Bot 1 as the customer-facing Telegram notification and marketing transport.
- Keep Bot 1 separate from Bot 2 seller registration and seller-chat notification responsibilities.
- Preserve the existing Telegram Mini App auth flow and avoid storing raw Telegram `initData`.
- Add a reliable recipient registry that records whether the platform has a usable customer `chat_id`.
- Support service notifications and marketing broadcasts with explicit consent, templates, audit logs, rate limits, retries, and delivery reports.
- Keep PostgreSQL as the source of truth while allowing Redis-backed queues or workers later.

## Non-goals

- No customer campaigns, mass sending, broadcast deliveries, or campaign UI in
  MVP Phase 1.
- No change to Mini App auth, Bot 2 seller auth, or existing seller bot
  management.
- No marketing messages to users without marketing opt-in.
- No attempt to message arbitrary Telegram users who have not interacted with Bot 1.
- No storage of raw Telegram `initData`, bot tokens, webhook secrets, or sensitive Telegram update payloads in logs.

## Implementation Status

MVP Phase 1 is implemented as a customer subscription registry, Bot 1 webhook,
Mini App Profile settings, and Seller Panel read-only listing. Phase 1.5 adds
customer-facing order service notifications through Bot 1, with a minimal
`CustomerServiceNotificationDelivery` attempt log for order-related service
messages only. Campaign, broadcast, scheduling, and marketing delivery models in
this document remain Phase 2 design notes only.

## Current State

The current Mini App auth implementation uses `WebApp.initData` at the UI boundary and posts it to `POST /api/v1/auth/telegram/login`. The backend validates the signed init data, extracts the `user` payload, upserts `User`, issues a JWT, and discards the raw init data.

Current customer `User` data from Mini App auth:

| Field | Current state |
| --- | --- |
| `telegram_id` | Stored on `users.telegram_id`, unique and required. |
| `username` | Stored when present in Telegram user payload. |
| `first_name` | Stored when present in Telegram user payload. |
| `last_name` | Stored when present in Telegram user payload. |
| `phone` | Stored only if Telegram user payload includes `phone` or `phone_number`; this is not a reliable Mini App auth field. |
| `chat_id` | Not stored for customer users. Mini App auth does not provide a bot chat id. |

Existing Telegram modules are seller-oriented:

- `backend/app/modules/telegram/` currently exposes Bot 2 webhook routes under `/api/v1/telegram/seller-bot/webhook`.
- `backend/app/modules/seller_bot/` manages Bot 2 status, seller-chat test messages, seller-chat MVP broadcast, and seller group commands.
- `backend/app/modules/seller_auth/` stores seller Telegram user/chat data because Bot 2 receives `/start seller_<token>` in a private chat.

Existing notifications:

- `Notification` records individual internal or Telegram notifications.
- Telegram delivery currently targets the configured seller notification chat through Bot 2 settings.
- Order checkout emits notification events after successful persistence.
- Seller/admin notification actions can already create `AuditLog` entries.

## Telegram Constraints

Bot 1 cannot safely message all current Mini App users immediately.

Telegram Mini App auth proves the user's Telegram identity for the Mini App session, but it does not prove that Bot 1 has a private chat with the user. A bot can send a private message only after the user has initiated interaction with that bot, commonly by opening the bot and sending `/start`, clicking a deep link, or otherwise creating a valid private chat update.

Required interaction to collect a valid Bot 1 `chat_id`:

1. User opens Bot 1 directly or through a deep link, for example `/start notify_<token>` or `/start`.
2. Telegram sends Bot 1 a webhook update with `message.chat.id` and `message.from.id`.
3. Backend verifies the webhook secret, matches `from.id` to an existing `User.telegram_id` when possible, and stores the private `chat_id`.
4. Backend records service and marketing consent state separately.

`telegram_id` and private `chat_id` are often the same for private chats, but the architecture should store `chat_id` from the webhook update instead of assuming equality.

## Proposed Data Model

Keep customer notification SQLAlchemy models in `backend/app/db/models.py` until
the model layer is split, following current project rules.

### CustomerTelegramSubscription

Purpose: customer Bot 1 recipient registry and consent source of truth.

Status: implemented in MVP Phase 1.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | Internal id. |
| `user_id` | FK `users.id`, unique, nullable | Nullable only for temporary unmatched webhook starts; normally linked to a user. |
| `telegram_user_id` | bigint, indexed | From webhook `message.from.id`; must match `users.telegram_id` before linking. |
| `telegram_chat_id` | bigint, nullable, indexed | From Bot 1 private chat update; required for sending. |
| `telegram_username` | string nullable | Last seen username from Bot 1 update. |
| `telegram_first_name` | string nullable | Last seen first name from Bot 1 update. |
| `telegram_last_name` | string nullable | Last seen last name from Bot 1 update. |
| `chat_type` | string | Must be `private` for customer sending. |
| `has_chat` | bool | True when private `telegram_chat_id` is known and not blocked. |
| `service_opt_in` | bool | Default true after valid `/start`; user can opt out except legally/operationally required messages if product policy allows. |
| `marketing_opt_in` | bool | Default false unless explicit consent is captured. |
| `opt_in_source` | string nullable | `bot_start`, `mini_app_profile`, `checkout`, etc. |
| `marketing_opted_in_at` | datetime nullable | Consent timestamp. |
| `marketing_opted_out_at` | datetime nullable | Last opt-out timestamp. |
| `service_opted_out_at` | datetime nullable | Last service opt-out timestamp. |
| `last_start_at` | datetime nullable | Last `/start`. |
| `last_stop_at` | datetime nullable | Last `/stop`. |
| `last_settings_at` | datetime nullable | Last `/settings` interaction. |
| `blocked_at` | datetime nullable | Set when Telegram returns 403 blocked/deactivated. |
| `last_delivery_error` | text nullable | Sanitized error summary only. |
| `created_at` | datetime | Creation timestamp. |
| `updated_at` | datetime | Update timestamp. |

Indexes and constraints:

- Unique on `user_id` when non-null.
- Unique on `telegram_user_id`.
- Index on `(has_chat, service_opt_in, marketing_opt_in)`.
- Index on `blocked_at`.

### NotificationTemplate

Purpose: reusable message templates for service and marketing sends.

Status: future Phase 2 scope.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | Internal id. |
| `key` | string unique | Example: `order.shipped.customer`, `marketing.drop_announcement`. |
| `name` | string | Seller Panel display name. |
| `category` | enum/string | `service` or `marketing`. |
| `channel` | enum/string | `telegram` for MVP. |
| `title` | string nullable | Internal/reporting title. |
| `body_template` | text | Telegram message text template. |
| `parse_mode` | string nullable | Prefer null/plain text for MVP; allow MarkdownV2 or HTML later with strict escaping. |
| `allowed_variables` | JSON/list | Explicit variables such as `first_name`, `order_number`, `promo_code`. |
| `is_active` | bool | Disabled templates cannot be used. |
| `created_by_user_id` | FK nullable | Seller/admin actor. |
| `updated_by_user_id` | FK nullable | Last editor. |
| `created_at` | datetime | Creation timestamp. |
| `updated_at` | datetime | Update timestamp. |

### BroadcastCampaign

Purpose: seller/admin-created customer campaign, including service or marketing sends.

Status: future Phase 2 scope. Do not add this model or campaign APIs in Phase 1.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | Internal id. |
| `template_id` | FK nullable | Optional template source. |
| `name` | string | Campaign name. |
| `type` | enum/string | `service` or `marketing`. |
| `status` | enum/string | `draft`, `scheduled`, `sending`, `paused`, `completed`, `cancelled`, `failed`. |
| `audience_filter` | JSON | Stored filter definition, not raw recipient list only. |
| `recipient_count_estimate` | integer | Count at preview/schedule time. |
| `recipient_count_final` | integer nullable | Count after delivery rows are created. |
| `message_title` | string nullable | Report title. |
| `message_body` | text | Rendered base body or copied template body. |
| `parse_mode` | string nullable | Telegram parse mode. |
| `scheduled_at` | datetime nullable | Future send time. |
| `started_at` | datetime nullable | First send timestamp. |
| `completed_at` | datetime nullable | Completion timestamp. |
| `created_by_user_id` | FK | Seller/admin actor. |
| `approved_by_user_id` | FK nullable | Optional second approval for marketing. |
| `cancelled_by_user_id` | FK nullable | Actor who cancelled. |
| `created_at` | datetime | Creation timestamp. |
| `updated_at` | datetime | Update timestamp. |

Recommended audience filters for MVP:

- All customers with Bot 1 chat and service opt-in.
- All customers with Bot 1 chat and marketing opt-in.
- Customers with at least one order.
- Customers who purchased a given product/category.
- Customers who used a given promo code.
- Manual test recipient by current seller/admin's linked Telegram account, if available.

### BroadcastDelivery

Purpose: one row per campaign recipient and delivery attempt state.

Status: future Phase 2 scope. Do not add this model or delivery queue in Phase 1.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | Internal id. |
| `campaign_id` | FK `broadcast_campaigns.id` | Parent campaign. |
| `user_id` | FK `users.id`, nullable | Recipient user. |
| `subscription_id` | FK `customer_telegram_subscriptions.id` | Recipient subscription snapshot source. |
| `telegram_chat_id` | bigint | Chat id snapshot used for delivery. |
| `status` | enum/string | `pending`, `sending`, `sent`, `failed`, `skipped`, `blocked`, `rate_limited`. |
| `attempt_count` | integer | Starts at 0. |
| `next_attempt_at` | datetime nullable | Retry scheduling. |
| `sent_at` | datetime nullable | Success timestamp. |
| `last_attempt_at` | datetime nullable | Last delivery attempt. |
| `telegram_message_id` | integer nullable | Telegram API result when available. |
| `error_code` | string nullable | Sanitized code: `blocked`, `retry_after`, `bad_request`, etc. |
| `error_message` | text nullable | Sanitized short message, no tokens or raw payloads. |
| `retry_after_seconds` | integer nullable | From Telegram 429 response. |
| `created_at` | datetime | Creation timestamp. |
| `updated_at` | datetime | Update timestamp. |

Indexes and constraints:

- Unique on `(campaign_id, subscription_id)`.
- Index on `(campaign_id, status)`.
- Index on `(status, next_attempt_at)`.

## Proposed API

Use a dedicated customer notification module such as `backend/app/modules/customer_notifications/`. Routers stay thin, services own business rules, repositories own SQLAlchemy queries.

Customer-facing Mini App endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/customer-notifications/me/subscription` | Return current user's Bot 1 chat/consent state. |
| `PATCH` | `/api/v1/customer-notifications/me/subscription` | Update service/marketing opt-in preferences from Mini App Profile settings. |
| `POST` | `/api/v1/customer-notifications/me/start-link` | Create a short-lived deep link payload for collecting Bot 1 chat id. |

Seller/admin endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/customer-notifications/subscriptions` | List/search recipient registry with consent and delivery state. |
| `GET` | `/api/v1/customer-notifications/templates` | List templates. |
| `POST` | `/api/v1/customer-notifications/templates` | Create template. |
| `PATCH` | `/api/v1/customer-notifications/templates/{template_id}` | Update template. |
| `GET` | `/api/v1/customer-notifications/campaigns` | List campaigns. |
| `POST` | `/api/v1/customer-notifications/campaigns` | Create draft campaign. |
| `GET` | `/api/v1/customer-notifications/campaigns/{campaign_id}` | Campaign details and summary. |
| `PATCH` | `/api/v1/customer-notifications/campaigns/{campaign_id}` | Edit draft or pause/cancel. |
| `POST` | `/api/v1/customer-notifications/campaigns/{campaign_id}/preview` | Render message and count eligible recipients. |
| `POST` | `/api/v1/customer-notifications/campaigns/{campaign_id}/test` | Send to a selected safe test recipient. |
| `POST` | `/api/v1/customer-notifications/campaigns/{campaign_id}/schedule` | Schedule or start a campaign. |
| `POST` | `/api/v1/customer-notifications/campaigns/{campaign_id}/process-batch` | MVP protected batch sender endpoint. |
| `GET` | `/api/v1/customer-notifications/campaigns/{campaign_id}/deliveries` | Paginated delivery report. |

Webhook endpoint:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/telegram/customer-bot/webhook` | Bot 1 webhook protected by Telegram secret header. |

Legacy path-secret routes should be avoided for Bot 1. Prefer the safe Telegram header `X-Telegram-Bot-Api-Secret-Token`.

MVP Phase 1 implements only the Mini App subscription endpoints, the
seller/admin subscription registry endpoint, and the Bot 1 webhook. Template,
campaign, preview, test-send, process-batch, and delivery-report endpoints are
Phase 2 design only.

## Bot 1 Webhook Design

Configuration names for future implementation should be distinct from Bot 2:

- `TELEGRAM_CUSTOMER_BOT_TOKEN`
- `TELEGRAM_CUSTOMER_BOT_USERNAME`
- `TELEGRAM_CUSTOMER_WEBHOOK_SECRET`
- Optional delivery settings such as `CUSTOMER_BOT_SENDS_PER_SECOND`

Webhook path:

- `POST /api/v1/telegram/customer-bot/webhook`
- Require `X-Telegram-Bot-Api-Secret-Token`.
- Compare with `TELEGRAM_CUSTOMER_WEBHOOK_SECRET` using constant-time comparison.
- Redact this path and secret in request logs, mirroring the existing seller webhook sanitization posture.

Command handling:

- `/start`: collect private `chat_id`, update last-seen Telegram fields, link by `from.id` to `User.telegram_id` when possible, set `has_chat=true`, set `service_opt_in=true`, do not set marketing opt-in unless the payload explicitly represents a marketing consent flow.
- `/start notify_<token>`: link a Mini App-generated token to the authenticated user, collect `chat_id`, enable service opt-in, and show settings buttons.
- `/start marketing_<token>`: collect `chat_id` and set marketing opt-in only if the token was generated from an explicit Mini App or checkout consent action.
- `/stop`: opt out of marketing and service sends, set stop timestamp, keep the subscription row for suppression and audit/reporting.
- `/settings`: send inline buttons for service notifications and marketing notifications.
- Unknown messages: respond with a compact settings/help message, not a marketing message.

Callback query handling:

- `customer_notifications:service:on`
- `customer_notifications:service:off`
- `customer_notifications:marketing:on`
- `customer_notifications:marketing:off`

Callbacks update consent state and respond with the current settings. They should not expose internal user ids or campaign details.

## Opt-in/Opt-out Design

Service notifications:

- Examples: order status updates, delivery updates, important account/service notices.
- Eligible only when `has_chat=true`, `telegram_chat_id` is present, `blocked_at is null`, and `service_opt_in=true`.
- `/start` may enable service notifications because the user has initiated Bot 1 interaction.
- `/stop` disables service notifications unless future legal/product policy defines a narrower class of mandatory transactional notices. For MVP, respect `/stop` fully.

Marketing notifications:

- Examples: new collection, sale, promo, abandoned favorites, win-back campaigns.
- Default false.
- Must require explicit opt-in from Mini App Profile settings, checkout checkbox, or Bot 1 settings callback.
- Marketing opt-in must record timestamp and source.
- `/stop` always disables marketing.
- Mini App Profile must show clear state: chat connected or not, service opt-in, marketing opt-in, and a Bot 1 link when chat is missing.

Recipient eligibility:

- Marketing campaigns must query only subscriptions with `marketing_opt_in=true`.
- Service campaigns must query only subscriptions with `service_opt_in=true`.
- Both must require known private `telegram_chat_id` and no active block flag.
- Unmatched webhook starts can be kept, but they are not broadcast recipients until linked to a `User`.

## Broadcast Delivery Design

MVP flow:

1. Seller/admin creates a draft campaign.
2. Backend validates campaign type, template variables, message length, and audience filter.
3. Seller/admin previews recipient count and message rendering.
4. Seller/admin sends a test message.
5. Seller/admin schedules or starts the campaign.
6. Backend materializes `BroadcastDelivery` rows from the eligible recipient query.
7. MVP batch processor sends a bounded page of pending deliveries.
8. Delivery report aggregates sent, failed, blocked, skipped, and pending counts.

Synchronous vs background:

- Do not send a full broadcast synchronously inside the create/schedule request.
- MVP may expose a protected `process-batch` endpoint for manual or cron-triggered processing.
- Future phase should move batch processing into Redis queue and a worker under `backend/app/jobs/`.

Message rendering:

- Render each recipient from a safe variable allowlist.
- Do not allow arbitrary database field interpolation.
- Apply Telegram text length limits before creating deliveries.
- Prefer plain text for MVP. If parse modes are added, escape variables before rendering.

Relationship to existing `Notification`:

- Keep `Notification` for individual system/internal notifications and seller Bot 2 history.
- Use `BroadcastCampaign` and `BroadcastDelivery` for customer campaign reporting.
- Optionally create a `Notification` row for service notification center visibility when the event is customer-specific, but do not rely on `Notification` alone for campaign delivery reports.

## Rate Limiting/Retry Design

Rate limits:

- Global Bot 1 sender limit: start conservatively, for example 20 messages/second per bot, configurable below Telegram's documented ceiling.
- Per-campaign throttle: cap messages per batch to avoid one campaign starving service notifications.
- Per-user cooldown for marketing: avoid repeated marketing sends within a configured window.
- API rate limits: protect preview, test send, schedule, and process-batch endpoints.

Retry policy:

- `403 Forbidden` or blocked/deactivated user: mark delivery `blocked`, set subscription `blocked_at`, set `has_chat=false`, clear active send eligibility, do not retry until user sends `/start` again.
- `429 Too Many Requests`: read `retry_after`, mark delivery `rate_limited`, set `next_attempt_at`, and pause or slow the campaign queue.
- Transient HTTP/network failures: retry with bounded exponential backoff, maximum attempts such as 3.
- Bad request due to message formatting: mark failed, stop the campaign if the same template failure repeats.
- Successful send: store `telegram_message_id` if returned, mark sent, set `sent_at`.

Ordering:

- Service notifications should have a higher priority queue than marketing.
- Campaigns should be pausable and cancellable.
- A cancelled campaign should skip remaining pending deliveries and preserve previous delivery rows.

## Seller Panel UX

Add a separate Seller Panel area, not part of `SellerBotPage`, for Bot 1 customer messaging. Suggested navigation label: `Customer Notifications`.

Required pages:

- Campaign list: status, type, created by, scheduled time, recipient count, sent/failed/blocked progress.
- Create campaign: type, template, audience filter, message body, schedule time, compliance/consent warning.
- Preview/test: rendered Telegram preview, variable sample, estimated recipients, explicit test-send action.
- Delivery report: delivery table with user, status, attempts, sent time, sanitized error, and filters.
- Templates: create/edit reusable service and marketing templates with allowed variables.
- Recipient list: searchable customer subscription registry showing chat known, service opt-in, marketing opt-in, blocked state, and last interaction.

UX rules:

- Marketing campaigns must show an eligibility count that excludes non-opted-in users.
- Sending controls should be disabled until preview count and test send are complete.
- The UI must make Bot 1 customer targeting visually distinct from Bot 2 seller-chat tooling.
- No bot token or webhook secret is ever shown in the frontend.

## Mini App UX

Use the existing Profile settings area as the customer-facing entry point.

Suggested Profile settings:

- `Telegram chat`: connected/not connected.
- `Order and service notifications`: toggle.
- `Marketing offers`: toggle, default off.
- `Open Bot 1`: button/deep link when chat is missing.
- `Privacy`: brief explanation that Telegram messages require opening Bot 1 and can be disabled with `/stop`.

Behavior:

- If the backend has no `telegram_chat_id`, toggling service or marketing opt-in should guide the user to Bot 1 with a short-lived deep link.
- Marketing toggle must include explicit consent language.
- `/stop` changes should be reflected when the Mini App refreshes subscription state.

## Audit/Security/Privacy

Audit actions:

- Template created/updated/disabled.
- Campaign created/updated/scheduled/started/paused/cancelled.
- Test message sent.
- Batch processing started/completed when manually triggered by seller/admin.
- Consent changed by seller/admin action if such an admin override is ever allowed. MVP should avoid admin overrides.

Audit metadata:

- Store actor user id, action, entity type/id, before/after snapshots, recipient counts, message length, campaign type, and source.
- Do not store bot tokens, webhook secrets, raw Telegram updates, or full sensitive user payloads.

Security/privacy rules:

- Bot 1 token and webhook secret stay backend-only.
- Do not log Authorization headers, bot tokens, webhook secrets, raw Telegram update bodies, or raw initData.
- Store only necessary Telegram identity fields and chat id.
- Store sanitized delivery errors.
- Respect `/stop` immediately.
- Marketing opt-in must be explicit and revocable.
- Recipient exports, if added later, should require ADMIN or a separate permission and should avoid exposing raw chat ids unless strictly needed.
- Campaign content should be stored because sellers/admins need auditability and delivery reports; avoid including sensitive personal data in templates.

## MVP Phase 1

Backend design scope for the first implementation sprint:

- Add `CustomerTelegramSubscription`.
- Add Bot 1 webhook endpoint with `/start`, `/stop`, `/settings`, and settings callbacks.
- Add customer subscription read/update APIs for Mini App Profile.
- Add a Seller/Admin subscription registry endpoint for read-only listing.
- Add audit logs for subscription state changes.
- Add tests for webhook secret validation, chat id collection, group-chat
  rejection, opt-in/opt-out, settings callbacks, and route authorization.

Frontend design scope:

- Mini App Profile notification settings and Bot 1 deep link.
- Seller Panel recipient list/status page.

This phase does not send marketing campaigns.

## MVP Phase 1.5

Backend implementation scope:

- Add `CustomerServiceNotificationDelivery` for customer service notification
  attempts tied to order events.
- Send order-created and order-status service notifications through Bot 1 only,
  using `TELEGRAM_CUSTOMER_BOT_TOKEN`.
- Reuse `CustomerTelegramSubscription` eligibility: linked user, private chat,
  known chat id, `has_chat=true`, `service_opt_in=true`, and no `blocked_at`.
- Record skipped, sent, failed, blocked, and rate-limit metadata with sanitized
  Telegram errors.
- Keep checkout/status updates successful if Bot 1 delivery fails.
- Keep marketing opt-in unchanged and do not add campaigns, scheduling, mass
  sending, seller-editable templates, or campaign UI.

## MVP Phase 2

Backend design scope:

- Add `NotificationTemplate`, `BroadcastCampaign`, and `BroadcastDelivery`.
- Add campaign CRUD, preview, test send, schedule, process-batch, and delivery report APIs.
- Add rate-limited Telegram sender for Bot 1 with retry handling.
- Add audit logs for campaign/template lifecycle.

Frontend design scope:

- Seller Panel campaign list, create campaign, preview/test, templates, and delivery report pages.
- Optional Mini App in-app notification center alignment with existing `Notification` records.

Future worker scope:

- Replace the MVP process-batch endpoint with Redis-backed background jobs and a dedicated worker.
- Add scheduling and priority queues for service vs marketing.

## Testing Plan

Backend tests:

- Telegram Mini App auth remains unchanged and still stores only current user fields.
- Bot 1 webhook rejects missing/wrong secret header.
- `/start` with private chat stores `telegram_chat_id` and links by Telegram user id.
- `/start` in a group does not create a customer subscription for broadcasts.
- `/stop` disables service and marketing eligibility.
- `/settings` callbacks update only the requesting user's subscription.
- Marketing campaign recipient query excludes users without marketing opt-in, users without chat id, and blocked users.
- Service campaign query excludes users without service opt-in, users without chat id, and blocked users.
- 403 delivery marks subscription blocked and delivery blocked.
- 429 delivery sets `retry_after_seconds` and `next_attempt_at`.
- Audit logs are created for template and campaign actions.
- Logs and persisted payloads do not include bot tokens, webhook secrets, raw initData, or raw webhook payload dumps.

Frontend tests/build checks:

- Mini App build after implementing Profile notification settings.
- Seller Panel build after implementing customer notification pages.
- UI states for connected/not connected chat, opted in/out, blocked, and loading/error states.

Manual smoke tests:

- Set Bot 1 webhook in staging using a safe script equivalent to the seller bot script.
- Open Mini App profile, generate Bot 1 link, send `/start`, confirm chat connected.
- Toggle marketing on/off and verify recipient eligibility.
- Open Seller Panel Customer Notifications and verify the subscription appears
  with masked chat metadata.

Phase 2 manual smoke tests:

- Send a test campaign to an internal test account.
- Run a small campaign batch and verify delivery report counts.

## Deployment Plan

Phase 1 deployment:

1. Add environment placeholders only in `.env.example`/production docs, never real secrets.
2. Run Alembic migration for `CustomerTelegramSubscription`.
3. Deploy backend with Bot 1 webhook route.
4. Configure Bot 1 webhook with Telegram `secret_token`.
5. Release Mini App Profile settings.
6. Monitor subscription creation, `/stop`, and blocked states.

Phase 2 deployment:

1. Run migrations for templates, campaigns, and deliveries.
2. Deploy campaign APIs and Seller Panel pages.
3. Start with test-send only in staging.
4. Enable small internal campaigns.
5. Enable marketing campaigns only after consent UX and suppression behavior are verified.
6. Add worker/Redis queue when batch endpoint throughput or scheduling needs grow.

Rollback:

- Disable campaign scheduling in Seller Panel.
- Pause campaigns by status.
- Keep subscription rows for suppression and future recovery.
- Keep Bot 1 webhook active for `/stop` and settings even if campaign sending is disabled.

## Open Questions

- Should service notifications default to enabled after `/start`, or should the Mini App require a separate service opt-in toggle before first send?
- Should marketing opt-in be allowed during checkout, or only in Profile/Bot 1 settings?
- Is a second approval required for marketing campaigns before production send?
- What is the exact customer audience model for MVP: all opted-in users, purchasers only, or segment filters by order/product/category?
- Should Bot 1 customer order status notifications be sent for every status change or only selected statuses such as `PROCESSING`, `SHIPPED`, and `DELIVERED`?
- Should customer `telegram_chat_id` be visible to admins, or masked in Seller Panel delivery reports?
- What retention period should be used for failed delivery rows and sanitized errors?
- Should service notifications create existing `Notification` rows for Mini App in-app history in addition to Bot 1 deliveries?
- Who can create and approve templates: SELLER, ADMIN, or ADMIN only for marketing?
