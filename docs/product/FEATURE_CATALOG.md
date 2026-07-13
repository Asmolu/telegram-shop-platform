# Каталог функций

Статусы: **Deployed**, **Implemented**, **Partial**, **Planned**, **Deprecated**,
**Unsupported**, **NEEDS VERIFICATION**.

| Area | Customer value | Entry | Backend / UI | Status | Tests | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| Auth/profile | Telegram sign-in, saved personal data | Mini App | `auth`, `users` | Deployed | auth/users tests | Telegram dependency |
| Catalog/variants | товары, prices, sizes, stock | feed/category/product | `products`; Product pages | Deployed | product/search tests | no bulk import |
| Categories/tags | discovery taxonomy | category/search | `categories`, `tags` | Deployed | taxonomy tests | manual curation |
| Search/aliases | typo-tolerant discovery | `/search*` | `products/search.py` | Deployed | search tests | PostgreSQL-specific |
| Looks | outfit composition | `/looks*` | `looks` | Deployed / Partial defaults | Look tests | all components initially selected |
| Favorites | saved products | product/profile | `favorites` | Deployed | favorite tests | JWT required |
| Cart | selected items/totals | `/cart` | `cart` | Deployed | cart tests | live, not reserved |
| Checkout/delivery | order placement | `/checkout` | `orders` | Deployed | checkout tests | manual fixed delivery |
| Promo | discount | cart/checkout | `promo_codes` | Deployed | promo tests | goods only |
| Order lifecycle | fulfillment visibility | profile/orders | `orders` | Deployed | order tests | non-linear correction |
| Manual SBP | payment evidence | `/payment/:id` | `manual_payments` | Deployed | payment tests | no provider |
| Returns/refunds | post-delivery request | `/orders/:id/return` | `returns` | Deployed / legal gap | return tests | 24h, manual refund |
| Reviews | verified purchase feedback | product/profile | `reviews` | Deployed | review tests | manual moderation |
| Banners | promotional navigation | main | `banners` | Deployed | banner tests | content approval manual |
| Telegram service sends | order updates | Bot 1 | `customer_notifications` | Deployed | notification tests | eligibility rules |
| In-app notifications | durable status popups | Mini App shell | `customer_in_app_notifications` | Deployed | backend/Mini tests | no bulk backfill |
| Campaigns | broadcasts | Seller `/customer-notifications` | campaigns | Deployed | campaign tests | private chat required |
| Channel entry | channel deep link | Seller `/channel-entry` | `channel_entry` | Deployed | channel tests | no private-chat state |
| Analytics/audit | diagnostics/accountability | Seller/admin | `analytics`, `audit` | Implemented | module tests | maturity/coverage partial |
| Catalog import | onboarding speed | none | none found | Unsupported | — | custom work |
| Acquiring/receipts | payment automation | none | none found | Unsupported | — | business/legal blocker |
| Multi-tenancy | shared SaaS | none | no tenant keys | Unsupported | — | separate deployment only |

Источник: `backend/app/modules/`, `mini-app/src/pages/`, `seller-panel/src/pages/`, `backend/tests/`.

