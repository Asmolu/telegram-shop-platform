from decimal import Decimal

from app.common.labels import delivery_method_label
from app.db.models import OrderDeliveryMethod

DELIVERY_PRICE_BY_METHOD: dict[OrderDeliveryMethod, Decimal] = {
    OrderDeliveryMethod.ROUTE_TAXI: Decimal("200.00"),
    OrderDeliveryMethod.CITY_DELIVERY: Decimal("300.00"),
    OrderDeliveryMethod.OZON: Decimal("200.00"),
    OrderDeliveryMethod.WB: Decimal("0.00"),
    OrderDeliveryMethod.CDEK: Decimal("0.00"),
    OrderDeliveryMethod.PICKUP: Decimal("0.00"),
}


def delivery_price_for_method(method: OrderDeliveryMethod) -> Decimal:
    return DELIVERY_PRICE_BY_METHOD[method]


def is_delivery_address_required(method: OrderDeliveryMethod) -> bool:
    return method != OrderDeliveryMethod.PICKUP


__all__ = [
    "DELIVERY_PRICE_BY_METHOD",
    "delivery_method_label",
    "delivery_price_for_method",
    "is_delivery_address_required",
]
