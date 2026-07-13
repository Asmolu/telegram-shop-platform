# Delivery

Статус: канонический источник prices/rules.

| API enum | Customer label | Price | Address required by intended helper | Current checkout reality |
| --- | --- | ---: | --- | --- |
| `ROUTE_TAXI` | Маршруткой | 200 ₽ | Yes | required |
| `CITY_DELIVERY` | Доставка по городу | 300 ₽ | Yes | required |
| `OZON` | Ozon | 200 ₽ | Yes | required |
| `WB` | ВБ | 0 ₽ | Yes | required |
| `CDEK` | СДЭК | 0 ₽ | Yes | required |
| `PICKUP` | Самовывоз | 0 ₽ | No | **required by schema/service** |

`is_delivery_address_required()` excludes Pickup, but `OrderCheckoutCreate.delivery_address` and
`OrdersService._validate_checkout_delivery` require non-empty text for every method. UI should send a
Pickup location/description until behavior changes.

Delivery price is snapshotted into Order and added after goods discount. Promo does not reduce delivery.
CDEK/WB zero price is current application configuration, not a promise that carrier service is free;
seller must explain any external/carrier payment note during onboarding.

**NEEDS VERIFICATION**: approved customer-facing CDEK/WB wording and exact Pickup address text are not
stored as business policy. Seller/product owner must confirm; blocks support/sales copy, not checkout.

Source: `orders/delivery.py`, `orders/schemas.py`, `orders/service.py`,
`common/labels.py`, checkout frontend/tests.

