# Product overview

ICON STORE — deployed storefront и seller operations platform для продаж через Telegram Mini App.
Customer выбирает catalog/Look, оформляет order, вручную оплачивает и получает notifications;
seller управляет content, fulfillment, payments, returns и communications.

Production snapshot: [../PRODUCTION_STATE.md](../PRODUCTION_STATE.md). Product не является
multi-tenant SaaS и не включает acquiring/ERP/fiscal integration.

| Surface | Назначение |
| --- | --- |
| Mini App | mobile-first discovery, cart, checkout, payment, returns, profile |
| Seller Panel | desktop catalog/orders/payments/returns/communications |
| Bot 1 | customer subscriptions, service/marketing sends, channel entry |
| Bot 2 | seller/admin/auth callbacks |
| API | business rules, persistence, auth, workers |

Источник: `mini-app/src/shared/router/RouterProvider.tsx`, `seller-panel/src/App.tsx`,
`backend/app/api/router.py`.

