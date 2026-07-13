# API reference

Generated and verified locally from FastAPI OpenAPI on 2026-07-13: **193 operations**.
Canonical runtime schemas remain local `/api/v1/openapi.json`, routers and Pydantic schemas.

Every Bearer endpoint can return 401 for missing/invalid JWT, 403 for inactive/insufficient role,
404 for absent/hidden/foreign resource, 409 for state/idempotency conflict, 422 for validation and
429 where rate limiting applies. Ownership is enforced in services/repositories. Mutations use async
SQLAlchemy transactions; external sends follow the module transaction/outbox rules.

| Method | Path | Purpose | Access / ownership | Request → response | Side effects / idempotency |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/dashboard/summary` | Get Dashboard Summary | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/analytics/telemetry` | Ingest Telemetry | Optional USER | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/analytics/events` | List Analytics Events | SELLER or ADMIN | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/analytics/summary` | Get Analytics Summary | SELLER or ADMIN | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/audit-logs` | List Audit Logs | ADMIN | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/audit-logs/{log_id}` | Get Audit Log | ADMIN | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/auth/telegram/login` | Telegram Login | Public auth (rate limited) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/seller-auth/register/start` | Start Registration | Public auth (rate limited) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/seller-auth/register/telegram-start` | Link Telegram Start | Public auth (rate limited) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/seller-auth/register/resend-code` | Resend Code | Public auth (rate limited) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/seller-auth/register/confirm` | Confirm Registration | Public auth (rate limited) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/seller-auth/login` | Login | Public auth (rate limited) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/seller-auth/me` | Read Current Seller | Bearer JWT; see router | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/seller-bot/status` | Get Status | Public / optional bearer | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/seller-bot/test-message` | Send Test Message | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/seller-bot/broadcast` | Broadcast | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/seller-bot/messages` | List Messages | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/settings/admin/payment-success-banner` | Get Payment Success Banner Settings | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/settings/admin/payment-success-banner` | Update Payment Success Banner Settings | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/settings/admin/payment-success-banner` | Delete Payment Success Banner Settings | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/settings/seller-contacts` | Get Public Seller Contact Settings | Public / optional bearer | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/settings/admin/seller-contacts` | Get Admin Seller Contact Settings | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PUT | `/api/v1/settings/admin/seller-contacts` | Update Admin Seller Contact Settings | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/telegram/status` | Module Status | Public / optional bearer | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/telegram/seller-bot/webhook` | Handle Seller Bot Webhook | Webhook secret + Telegram checks | `-` → `-` | Telegram callback; state mutation depends on update |
| POST | `/api/v1/telegram/customer-bot/webhook` | Handle Customer Bot Webhook | Webhook secret + Telegram checks | `-` → `-` | Telegram callback; state mutation depends on update |
| POST | `/api/v1/telegram/seller-bot/webhook/{secret}` | Handle Legacy Seller Bot Webhook | Webhook secret + Telegram checks | `-` → `-` | Telegram callback; state mutation depends on update |
| GET | `/api/v1/users/me` | Read Current User | USER, owned resource | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/users/me/personal-data` | Read Current User Personal Data | USER, owned resource | `-` → `-` | Read; no business mutation |
| PUT | `/api/v1/users/me/personal-data` | Update Current User Personal Data | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/users/admin` | List Users | ADMIN | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/users/admin/blocks` | List User Blocks | ADMIN | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/users/admin/blocks` | Create User Block | ADMIN | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/users/admin/blocks/{block_id}/unblock` | Unblock User | ADMIN | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/users/admin/{user_id}` | Get User Detail | ADMIN | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/banners` | List Public Banners | Bearer JWT; see router | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/banners/{banner_id}/click` | Track Banner Click | Bearer JWT; see router | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/banners/admin` | List Banners | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/banners/admin` | Create Banner | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/banners/admin/{banner_id}` | Get Banner | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/banners/admin/{banner_id}` | Update Banner | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/banners/admin/{banner_id}/activate` | Activate Banner | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/banners/admin/{banner_id}/deactivate` | Deactivate Banner | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/cart` | Get Current User Cart | USER, owned resource | `-` → `-` | Read; no business mutation |
| DELETE | `/api/v1/cart` | Clear Current User Cart | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/cart/items` | Add Item To Cart | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/cart/items` | Clear Cart | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/cart/items/{item_id}` | Update Cart Item Quantity | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/cart/items/{item_id}` | Remove Cart Item | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/cart/items/{item_id}/selection` | Update Cart Item Selection | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/cart/selection` | Update Cart Selection | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/orders/checkout` | Checkout Current User Cart | Bearer JWT; see router | `-` → `-` | Atomic order/stock/payment/CouponUsage/outbox; Idempotency-Key |
| GET | `/api/v1/orders` | List Current User Orders | USER, owned resource | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/orders/payment-success-banner/pending` | Get Pending Payment Success Banner | Bearer JWT; see router | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/orders/admin` | List Orders | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/orders/admin/{order_id}` | Get Order | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/orders/admin/{order_id}/status` | Update Order Status | Public / optional bearer | `-` → `-` | TX + audit + outbox + in-app/Telegram |
| POST | `/api/v1/orders/admin/{order_id}/customer-message` | Send Order Customer Message | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/orders/{order_id}/payment-success-banner/seen` | Mark Payment Success Banner Seen | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/orders/{order_id}` | Get Current User Order | USER, owned resource | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/outbox/admin/diagnostics` | Diagnostics | ADMIN | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/outbox/admin/{event_id}/retry` | Retry Failed Event | ADMIN | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/orders/{order_id}/return-eligibility` | Get Return Eligibility | USER, owned resource | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/orders/{order_id}/returns` | Create Return Request | USER, owned resource | `-` → `-` | TX; attachments/stock/refund by operation; in-app; create seller post-commit |
| POST | `/api/v1/returns/{return_request_id}/cancel` | Cancel Customer Return Request | USER, owned resource | `-` → `-` | TX; attachments/stock/refund by operation; in-app; create seller post-commit |
| GET | `/api/v1/returns/admin` | List Admin Return Requests | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/returns/admin/{return_request_id}` | Get Admin Return Request | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/returns/admin/{return_request_id}/approve` | Approve Return Request | SELLER or ADMIN (router-specific) | `-` → `-` | TX; attachments/stock/refund by operation; in-app; create seller post-commit |
| POST | `/api/v1/returns/admin/{return_request_id}/reject` | Reject Return Request | SELLER or ADMIN (router-specific) | `-` → `-` | TX; attachments/stock/refund by operation; in-app; create seller post-commit |
| POST | `/api/v1/returns/admin/{return_request_id}/complete` | Complete Return Request | SELLER or ADMIN (router-specific) | `-` → `-` | TX; attachments/stock/refund by operation; in-app; create seller post-commit |
| POST | `/api/v1/returns/admin/{return_request_id}/process` | Process Return Request | SELLER or ADMIN (router-specific) | `-` → `-` | TX; attachments/stock/refund by operation; in-app; create seller post-commit |
| POST | `/api/v1/returns/admin/{return_request_id}/cancel` | Cancel Admin Return Request | SELLER or ADMIN (router-specific) | `-` → `-` | TX; attachments/stock/refund by operation; in-app; create seller post-commit |
| GET | `/api/v1/feed` | List Public Feed | Public / optional bearer | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/looks/admin` | List Admin Looks | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/looks/admin` | Create Admin Look | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/looks/admin/slugs/next` | Generate Look Slugs | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/looks/admin/{look_id}` | Get Admin Look | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/looks/admin/{look_id}` | Update Admin Look | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/looks/admin/{look_id}` | Archive Admin Look | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/looks/admin/{look_id}/images` | Upload Admin Look Image | SELLER or ADMIN (router-specific) | `-` → `-` | Validated file write + DB update |
| DELETE | `/api/v1/looks/admin/{look_id}/images/{image_id}` | Delete Admin Look Image | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/looks` | List Public Looks | Public / optional bearer | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/looks/{slug}` | Get Public Look | Public / optional bearer | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/looks/{slug}/similar-products` | List Look Similar Products | Public / optional bearer | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/looks/{slug}/cart` | Add Look To Cart | Bearer JWT; see router | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/orders/{order_id}/payment` | Get Order Payment | USER, owned resource | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/orders/{order_id}/payment/submit` | Submit Order Payment | USER, owned resource | `-` → `-` | TX + outbox + in-app/Telegram; Idempotency-Key |
| POST | `/api/v1/orders/{order_id}/payment/receipt` | Upload Order Payment Receipt | USER, owned resource | `-` → `-` | Validated file write + DB update |
| GET | `/api/v1/seller/settings/payment` | Get Payment Settings | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PUT | `/api/v1/seller/settings/payment` | Update Payment Settings | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/seller/payments` | List Manual Payments | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/seller/payments/expire-due` | Expire Due Manual Payments | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/seller/payments/{payment_id}` | Get Manual Payment | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/seller/payments/{payment_id}/approve` | Approve Manual Payment | SELLER or ADMIN (router-specific) | `-` → `-` | TX + order/stock + outbox + in-app/Telegram |
| POST | `/api/v1/seller/payments/{payment_id}/reject` | Reject Manual Payment | SELLER or ADMIN (router-specific) | `-` → `-` | TX + order/stock + outbox + in-app/Telegram |
| POST | `/api/v1/promo-codes/validate` | Validate Current Cart Promo Code | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/promo-codes` | Create Promo Code | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/promo-codes` | List Promo Codes | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/promo-codes/{promo_code_id}` | Get Promo Code | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/promo-codes/{promo_code_id}` | Update Promo Code | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/promo-codes/{promo_code_id}` | Deactivate Promo Code | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/reviews/me` | List Current User Reviews | USER, owned resource | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/reviews/admin` | List Reviews | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/reviews/admin/{review_id}` | Get Review | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/reviews/admin/{review_id}/approve` | Approve Review | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/reviews/admin/{review_id}/reject` | Reject Review | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/reviews/{review_id}/status` | Moderate Review | Public / optional bearer | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/products/{product_id}/reviews` | Create Product Review | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/products/{product_id}/reviews` | List Approved Product Reviews | Public / optional bearer | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/favorites` | List Current User Favorites | USER, owned resource | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/favorites` | Add Favorite | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/favorites/{product_id}` | Remove Favorite | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/notifications/status` | Module Status | Public / optional bearer | `-` → `object` | Read; no business mutation |
| GET | `/api/v1/notifications/me` | List Current User Notifications | Bearer JWT; see router | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/notifications/admin` | List Notifications | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/notifications/admin/{notification_id}` | Get Notification | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/notifications/admin/{notification_id}/retry` | Retry Notification | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/categories` | List Categories | Public / optional bearer | `-` → `array` | Read; no business mutation |
| POST | `/api/v1/categories` | Create Category | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/categories/resolve` | Resolve Category | Public / optional bearer | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/categories/{category_id}` | Get Category | Public / optional bearer | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/categories/{category_id}` | Update Category | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/categories/{category_id}` | Delete Category | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/channel-entry/config` | Get Config | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/channel-entry/channels` | List Channels | SELLER or ADMIN (router-specific) | `-` → `array` | Read; no business mutation |
| POST | `/api/v1/channel-entry/channels` | Create Channel | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/channel-entry/channels/check` | Check Channel | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/channel-entry/channels/{channel_id}` | Update Channel | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/channel-entry/channels/{channel_id}` | Disable Channel | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/channel-entry/preview` | Preview | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/channel-entry/photos` | Upload Photo | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/channel-entry/publish` | Publish | SELLER or ADMIN (router-specific) | `-` → `-` | TX + Bot 1 channel call |
| POST | `/api/v1/channel-entry/messages/{message_id}/pin` | Pin Message | SELLER or ADMIN (router-specific) | `-` → `-` | TX + Bot 1 channel call |
| GET | `/api/v1/channel-entry/history` | History | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/customer-notifications/me/subscription` | Get My Subscription | USER, owned resource | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/customer-notifications/me/subscription` | Update My Subscription | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/me/write-access` | Record My Write Access | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/me/start-link` | Create My Start Link | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/customer-notifications/subscriptions` | List Subscriptions | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/customer-notifications/service-deliveries` | List Service Deliveries | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/customer-in-app-notifications/pending` | Pending | USER, owned resource | `-` → `array` | Read; no business mutation |
| POST | `/api/v1/customer-in-app-notifications/{notification_id}/seen` | Mark Seen | USER, owned resource | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/templates` | Create Template | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/customer-notifications/templates` | List Templates | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/customer-notifications/templates/{template_id}` | Get Template | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/customer-notifications/templates/{template_id}` | Update Template | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/templates/{template_id}/disable` | Disable Template | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/campaigns` | Create Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/customer-notifications/campaigns` | List Campaigns | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/customer-notifications/campaigns/{campaign_id}` | Get Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/customer-notifications/campaigns/{campaign_id}` | Update Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/campaigns/{campaign_id}/image` | Attach Campaign Image | SELLER or ADMIN (router-specific) | `-` → `-` | Validated file write + DB update |
| DELETE | `/api/v1/customer-notifications/campaigns/{campaign_id}/image` | Remove Campaign Image | SELLER or ADMIN (router-specific) | `-` → `-` | Validated file write + DB update |
| POST | `/api/v1/customer-notifications/campaigns/{campaign_id}/preview` | Preview Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/campaigns/{campaign_id}/test` | Send Test Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | TX + Bot 1 delivery/materialization |
| POST | `/api/v1/customer-notifications/campaigns/{campaign_id}/schedule` | Schedule Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/campaigns/{campaign_id}/start` | Start Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | TX + Bot 1 delivery/materialization |
| POST | `/api/v1/customer-notifications/campaigns/{campaign_id}/pause` | Pause Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/campaigns/{campaign_id}/cancel` | Cancel Campaign | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| POST | `/api/v1/customer-notifications/campaigns/{campaign_id}/process-batch` | Process Campaign Batch | SELLER or ADMIN (router-specific) | `-` → `-` | TX + Bot 1 delivery/materialization |
| GET | `/api/v1/customer-notifications/campaigns/{campaign_id}/deliveries` | List Campaign Deliveries | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/customer-notifications/campaigns/{campaign_id}/delivery-summary` | Get Campaign Delivery Summary | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/tags` | List Tags | Public / optional bearer | `-` → `array` | Read; no business mutation |
| POST | `/api/v1/tags` | Create Tag | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/tags/{tag_id}` | Get Tag | Public / optional bearer | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/tags/{tag_id}` | Update Tag | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/tags/{tag_id}` | Delete Tag | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/products` | List Public Products | Public / optional bearer | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/products` | Create Product | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/products/suggestions` | List Product Search Suggestions | Public / optional bearer | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/products/resolve` | Resolve Public Product | Bearer JWT; see router | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/products/admin` | List Products | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/products/admin/variant-skus/next` | Generate Variant Skus | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/products/admin/slugs/next` | Generate Product Slugs | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/products/admin/{product_id}` | Get Product | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/products/admin/{product_id}/variants` | List Product Variants | SELLER or ADMIN (router-specific) | `-` → `-` | Read; no business mutation |
| GET | `/api/v1/products/{product_id}/variants` | List Public Product Variants | Public / optional bearer | `-` → `-` | Read; no business mutation |
| POST | `/api/v1/products/{product_id}/variants` | Create Product Variant | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/products/{product_id}/similar` | List Similar Products | Public / optional bearer | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/products/variants/{variant_id}` | Update Product Variant | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/products/variants/{variant_id}` | Delete Product Variant | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/products/variants/{variant_id}/deactivate` | Deactivate Product Variant | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/products/{product_id}/status` | Update Product Status | Public / optional bearer | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| PATCH | `/api/v1/products/{product_id}/archive` | Archive Product | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/products/{product_id}` | Get Public Product | Public / optional bearer | `-` → `-` | Read; no business mutation |
| PATCH | `/api/v1/products/{product_id}` | Update Product | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| DELETE | `/api/v1/products/{product_id}` | Delete Product | SELLER or ADMIN (router-specific) | `-` → `-` | Domain transaction; audit/cache/notification where service defines |
| GET | `/api/v1/uploads/status` | Module Status | Public / optional bearer | `-` → `object` | Read; no business mutation |
| POST | `/api/v1/uploads/products/{product_id}/images` | Upload Product Image | Bearer JWT; see router | `-` → `-` | Validated file write + DB update |
| POST | `/api/v1/uploads/banners/images` | Upload Banner Image | Bearer JWT; see router | `-` → `-` | Validated file write + DB update |
| POST | `/api/v1/uploads/tags/images` | Upload Tag Image | Bearer JWT; see router | `-` → `-` | Validated file write + DB update |
| POST | `/api/v1/uploads/categories/images` | Upload Category Image | Bearer JWT; see router | `-` → `-` | Validated file write + DB update |
| GET | `/health` | Health Check | Public / optional bearer | `-` → `object` | Read; no business mutation |

## Contract notes

- Public reads may show optional OAuth2 in OpenAPI due to `get_optional_current_user`.
- Multipart endpoints use generated OpenAPI body schemas for form/files.
- Field validation: module `schemas.py`; lifecycle/side effects: `service.py`; locks/ownership:
  `repository.py`.
- Access labels summarize current dependencies; router source remains authoritative for each operation.
- No examples contain personal data or credentials.

Sources: `backend/app/main.py`, `backend/app/api/router.py`, module routers/schemas/services,
local `app.openapi()` output.

