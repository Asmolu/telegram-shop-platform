# UI Design Specification - StyleXac

This document defines current UI behavior and visual direction for the customer Mini App and Seller Panel.

## Product Surfaces

| Surface | Domain | Design posture |
| --- | --- | --- |
| Mini App | `https://mini.stylexac.ru` and `https://stylexac.ru` | Mobile-first, marketplace-like, Telegram WebView friendly |
| Seller Panel | `https://seller.stylexac.ru` | Desktop-first, dense dashboard for repeated operations |

The Mini App and Seller Panel must not look identical. They share product data and backend contracts, but they serve different users and usage patterns.

## Mini App Principles

- Mobile-first layout.
- Fast product discovery.
- Clear product imagery.
- Bottom navigation suited for Telegram WebView.
- Safe behavior when Telegram APIs are unavailable in local browser development.
- Telegram SDK/WebApp calls only at the UI boundary.
- No hardcoded production API URLs.

## Mini App Routes and Flows

Implemented customer flows:

- feed
- category
- search
- product detail
- cart
- profile
- checkout

### Feed, Category, and Search

- Product cards must prioritize image, title, brand/metadata where available, price, discount state, and add/cart action.
- Floating help widget `Как совершить заказ?` appears on feed/category/search.
- The help widget is draggable.
- The help widget can be hidden or swiped to the screen side.
- A side tab remains visible after hiding.
- Tapping the side tab restores the widget.

### Product Detail

- Product brand appears above the product title.
- If brand duplicates title text, UI should avoid awkward duplicate presentation.
- Size helper copy is: `Мы подбираем размер по росту и весу.`
- Product images, variants, price, old price, badges, and stock state should remain readable on mobile.

### Cart

- Promo code input must be keyboard-safe in Telegram WebView.
- Delivery price note is: `Цена сформирована без учёта стоимости доставки.`
- Totals, discounts, and checkout action must remain visible and understandable on narrow screens.

### Checkout

- Checkout must clearly preserve order totals, promo code result, customer fields, and manual payment state where applicable.
- Notification write-access prompts must be triggered only after user action.

### Profile

- Profile notification state should distinguish service notification availability from marketing subscription.
- Write access enables service notifications and does not imply marketing consent.

## Discount Badge Tiers

Discount badge visual sizing is tiered by discount percentage:

| Tier | Discount range |
| --- | --- |
| Tier 1 | `1-20%` |
| Tier 2 | `21-40%` |
| Tier 3 | `41-60%` |
| Tier 4 | `61-80%` |
| Tier 5 | `81-99%` |

Custom badge visual sizing should preserve legibility and avoid covering critical product image content.

## Banner UI

Implemented banner display types:

- `horizontal`
- `vertical`
- `popup`
- `aggressive_popup`

Current crop profiles:

| Banner type | Ratio |
| --- | --- |
| Horizontal native banner | `400:207` |
| Vertical banner | `9:16` |
| Popup banner | `3:4` |
| Aggressive popup | `9:16` |

Aggressive popup is an entry overlay pattern. It must remain dismissible and must not permanently block core navigation.

## Seller Panel Principles

- Desktop-first layout.
- Dashboard-like density.
- Clear navigation for repeated seller/admin work.
- Tables, forms, filters, previews, and status chips should be optimized for scanning.
- Avoid marketplace-style mobile composition in the Seller Panel.
- Avoid decorative landing-page hero sections for operational screens.

## Seller Panel Routes and Areas

Implemented operational areas:

- product management
- product variant matrix
- product image uploads
- badge preview where product-image badges are edited
- category/tag related catalog data through backend-supported flows
- banners
- promo codes
- customer notifications
- channel entry publishing
- seller/admin auth-related flows
- settings where implemented

### Product Management

- Product forms must support brand, title, description, price, old price, visibility/status, categories, tags, search aliases, images, variants, and inventory fields exposed by the backend.
- Variant matrix should make size/color/stock/SKU state easy to scan.
- Product image uploads should use the current crop/validation expectations.

### Banners

- Seller Panel must expose banner display type and matching crop behavior.
- Preview should help the seller understand how horizontal, vertical, popup, and aggressive popup banners will appear.

### Promo Codes

- Promo code UI must expose discount type, discount amount, usage limit, per-user limit, active state, and date windows where supported.

### Customer Notifications

- Seller Panel should represent Bot 1 as the customer notification bot.
- Customer notifications should distinguish service notification eligibility from marketing eligibility.
- Campaign flows should expose image support, preview/test send, status, and delivery reports where implemented.
- Backend template tables and endpoints exist; current UI is simplified and does not expose every backend template-management capability as a full template editor.

### Channel Entry

- Route: `/channel-entry`.
- The UI publishes through Bot 1.
- It must explain channel target, message, button, pin state, and history clearly.
- Channel button uses URL link to Mini App `startapp`.
- Do not present a Telegram `web_app` button as the channel-post mechanism.

## Accessibility and Responsiveness

- Text must fit inside controls on narrow screens.
- Buttons and interactive targets must be large enough for touch in the Mini App.
- Seller Panel controls can be denser, but labels and validation errors must remain readable.
- Do not overlap text, controls, product images, banners, or sticky navigation.

## Visual Asset Rules

- Product, banner, and campaign visuals should show the actual product or message subject.
- Avoid dark, blurred, stock-like, or purely atmospheric imagery when the user needs to inspect the real product.
- Static uploads are served through backend/reverse proxy paths.

## Current Checks

Mini App:

```bash
cd mini-app
npm test -- --run
npm run build
npm run verify:bundle
```

Seller Panel:

```bash
cd seller-panel
npm run lint
npm run typecheck
npm test -- --run
npm run build
```
