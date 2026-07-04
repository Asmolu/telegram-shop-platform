# Seller Panel

Desktop-first seller/admin dashboard for StyleXac.

## Current Production

| Area | Value |
| --- | --- |
| Domain | `https://seller.stylexac.ru` |
| API | `https://api.stylexac.ru` |
| Production server | Aeza Frankfurt |

## Stack

- React
- Vite
- TypeScript
- TypeScript build checks
- Node test runner for focused UI/domain tests

## Implemented Areas

- seller/admin auth-related flows
- product management
- product visibility, returnability, and size type controls
- product variant matrix
- product image uploads
- order management
- returns list/detail, approve/reject, complete/cancel, refund/restock processing
- Looks list/create/edit/archive, components, slug autofill, image upload
- product image badge preview where edited
- banners
- promo codes
- customer notifications
- customer campaigns and delivery reports
- channel entry publishing
- settings where implemented

## Design Direction

Seller Panel is desktop-first and dashboard-like. It must not visually mirror the customer Mini App.

Use dense but readable operational UI:

- tables
- filters
- forms
- status chips
- previews
- confirmations for critical actions

Avoid marketplace-style mobile composition for Seller Panel pages.

## Channel Entry

Route:

```text
/channel-entry
```

Behavior:

- uses Bot 1
- publishes and optionally pins a channel message
- uses URL button to Mini App `startapp`
- stores history with Telegram `message_id` and pin status
- does not use Telegram `web_app` button for channel posts

Default current link:

```text
https://t.me/CheckYouStyleBot?startapp=channel_pin
```

## Customer Notifications

Seller Panel uses customer-notification backend APIs for:

- subscription visibility
- campaign creation and management
- campaign image support
- preview/test send
- delivery reports

Bot 1 is the customer notification bot. Bot 2 must not be used for customer/channel buyer notification flows.

Template tables and backend endpoints exist. The current Seller Panel UI is simplified and does not expose every backend template-management capability as a full template editor.

## Environment

Use environment variables:

```text
VITE_API_BASE_URL=/api/v1
```

Production compose can pass:

```text
SELLER_PANEL_VITE_API_BASE_URL=/api/v1
```

Do not hardcode `https://api.stylexac.ru` in source.

## Checks

```bash
npm install
npm run lint
npm run typecheck
npm test -- --run
npm run build
```

## Related Docs

- `../UI_DESIGN_SPEC.README.md`
- `../docs/ARCHITECTURE.md`
- `../docs/CUSTOMER_NOTIFICATIONS_ARCHITECTURE.md`
- `../docs/TELEGRAM_CHANNEL_ENTRY.md`
- `../docs/TESTING.md`
