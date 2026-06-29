# Mini App

Customer Telegram Mini App for StyleXac.

## Current Production

| Area | Value |
| --- | --- |
| Main entry | `https://stylexac.ru` |
| Direct domain | `https://mini.stylexac.ru` |
| API | `https://api.stylexac.ru` |
| Bot 1 username | `CheckYouStyleBot` |

## Stack

- React
- Vite
- TypeScript
- Vitest
- Telegram WebApp APIs at the UI boundary

## Implemented Flows

- feed
- category
- search
- product detail
- cart
- profile
- checkout

## Current UI Behavior

- Marketplace-style mobile-first layout.
- Bottom navigation for Telegram WebView.
- Floating help widget `Как совершить заказ?` on feed/category/search.
- Help widget is draggable, can be hidden/swiped to screen side, leaves a side tab, and restores on tab tap.
- Product detail displays brand above title.
- Product detail size note: `Мы подбираем размер по росту и весу.`
- Cart delivery-price note: `Цена сформирована без учёта стоимости доставки.`
- Cart promo input is keyboard-safe.
- Discount badge tiers: `1-20%`, `21-40%`, `41-60%`, `61-80%`, `81-99%`.

## Auth and Session Behavior

- Waits for `Telegram.WebApp.initData` before login.
- Deduplicates in-flight Telegram login.
- Coordinates backend API `401` refresh and replays once after refresh.
- Keeps auth diagnostics sanitized.
- Raw `initData` is sent only to backend auth and must not be logged in frontend diagnostics.

## Notifications

Mini App write access:

- is requested only after a user action
- posts result to `POST /api/v1/customer-notifications/me/write-access`
- enables service notifications when granted
- does not silently enable marketing

If the user entered from channel entry without a private Bot 1 chat, write access is the current service-notification path.

## Environment

Use environment variables. Do not hardcode production API URLs.

```text
VITE_API_BASE_URL=/api/v1
VITE_TELEGRAM_BOT_USERNAME=CheckYouStyleBot
VITE_TELEMETRY_DISABLED=false
VITE_APP_VERSION=<SECRET>
```

Production compose can pass:

```text
MINI_APP_VITE_API_BASE_URL=/api/v1
VITE_TELEGRAM_BOT_USERNAME=CheckYouStyleBot
```

## Checks

```bash
npm install
npm test -- --run
npm run build
npm run verify:bundle
```

## Related Docs

- `../UI_DESIGN_SPEC.README.md`
- `../docs/ARCHITECTURE.md`
- `../docs/CUSTOMER_NOTIFICATIONS_ARCHITECTURE.md`
- `../docs/TELEGRAM_CHANNEL_ENTRY.md`
- `../docs/TESTING.md`
