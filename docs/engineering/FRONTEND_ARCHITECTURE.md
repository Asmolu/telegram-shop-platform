# Frontend architecture

Mini App and Seller Panel are separate React/TypeScript/Vite builds and must not look identical.
Mini App is mobile-first marketplace UI; Telegram SDK calls stay at UI boundary. Seller Panel is
desktop-first dashboard with explicit navigation.

Mini App routes: `/`, `/main`, `/categories`, `/category/:slug`, category product aliases,
`/search`, `/search/results`, `/product/:idOrSlug`, `/looks`, `/looks/:slug`, `/cart`, `/checkout`,
`/order-success/:id`, `/payment/:id`, `/orders/:id/return`, `/profile`, `/profile/personal-data`,
`/faq`. Seller routes: dashboard, orders, products/editor, taxonomy, banners, promo, reviews,
returns, blocks, Looks, statistics, customer notifications, channel entry, seller bot and settings.

API base is build-time `VITE_API_BASE_URL`; production URLs must not be hardcoded. Mini App auth
coordinates Telegram initData/JWT refresh. UI design authority: `UI_DESIGN_SPEC.README.md`.

Sources: `mini-app/src/App.tsx`, `mini-app/src/shared/router/RouterProvider.tsx`,
`seller-panel/src/App.tsx`, both `package.json`.

