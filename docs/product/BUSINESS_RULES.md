# Business rules

Статус: канонический. Ссылки на specialized lifecycle documents имеют приоритет.

## Catalog

Product lifecycle enum: `DRAFT`, `ACTIVE`, `OUT_OF_STOCK`, `ARCHIVED`. Только `ACTIVE` может участвовать в публичной выдаче; `is_listed` дополнительно управляет discovery, но не является security boundary.

- Public lists: только `ProductStatus.ACTIVE` и `is_listed=true`.
- ACTIVE `is_listed=false` не виден feed/category/search/suggestions/similar, но direct detail по
  id/slug доступен. Hidden ACTIVE product разрешен в Looks.
- Product имеет primary legacy category и до трех `ProductCategory` assignments с unique priority.
- Variant должен принадлежать product, быть active и иметь достаточный `available_quantity`.
- `is_returnable` копируется в `OrderItem` при checkout.

Источник: `products/repository.py`, `products/service.py`, `feed/repository.py`,
`looks/service.py`, `backend/tests/test_looks.py`.

## Cart, checkout, promo

- Cart и items принадлежат одному user; quantity positive и не превышает stock minus reserved.
- Checkout берет только selected items и требует хотя бы один.
- Required: recipient, phone, delivery method, non-empty address, integer height `1..300`,
  decimal weight `>0..1000`. Optional: Telegram username, delivery/customer comment.
- Explicit measurement fields имеют приоритет над legacy lines в `delivery_comment`.
- Promo is case-normalized; validates active window and global/per-user usage. Discount capped at
  goods subtotal. Delivery is added after discount.
- `Idempotency-Key` replays identical checkout/payment submission and rejects conflicting payload.

Источник: `orders/schemas.py`, `orders/service.py`, `promo_codes/service.py`, `idempotency/service.py`.

## Orders/payments/returns

Canonical rule: [ORDER_LIFECYCLE.md](ORDER_LIFECYCLE.md),
[PAYMENT_LIFECYCLE.md](PAYMENT_LIFECYCLE.md),
[RETURNS_AND_REFUNDS.md](RETURNS_AND_REFUNDS.md).

## Notifications

Persistence precedes external delivery. Order/payment outbox records commit with domain state.
Customer Telegram eligibility is distinct from marketing consent. Canonical rule:
[NOTIFICATIONS.md](NOTIFICATIONS.md).

## Catalog integrity gaps

`ONE_SIZE` означает accessory-like behavior в UI, но category/type restriction «только аксессуары»
не enforced. `is_default_selected` у Look хранится/валидируется, но current public response и Mini App
инициализируют все components selected. Эти facts нельзя скрывать в sales/demo.
