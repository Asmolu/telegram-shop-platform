# Changelog

All notable project changes are tracked here. Dates use ISO format.

## Unreleased

- Rewrote project documentation for the current StyleXac production state.
- Documented current domains: `stylexac.ru`, `mini.stylexac.ru`, `api.stylexac.ru`, `seller.stylexac.ru`.
- Documented Aeza Frankfurt production operations at `/opt/telegram-shop`.
- Documented current migration head `20260628_0039`.
- Documented Bot 1 write-access flow for order/service notifications.
- Documented customer campaign delivery eligibility and reports.
- Documented Seller Panel `/channel-entry` flow.
- Documented Mini App draggable help widget, cart delivery-price note, product detail size note, brand display, and discount badge tiers.
- Documented Caddy HTTP/3/QUIC disabled state and MSS clamp service.

## 2026-06-28

- Deployed production commit `6245489 Add Bot 1 write access flow for order notifications`.
- Added Mini App write-access persistence for customer service notifications.
- Updated service notification target resolution to support Bot 1 write-access users without silently enabling marketing.
- Kept Bot 1 customer responsibilities separated from Bot 2 seller/admin responsibilities.

## Historical

- Initialized the FastAPI backend scaffold.
- Added product catalog models, category/tag/product APIs, uploads, cart, orders, promo codes, reviews, seller/admin flows, analytics, manual payments, banners, customer notifications, and production deployment support over multiple implementation increments.
