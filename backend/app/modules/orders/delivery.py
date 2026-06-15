from app.db.models import OrderDeliveryMethod

ORDER_DELIVERY_METHOD_LABELS: dict[OrderDeliveryMethod, str] = {
    OrderDeliveryMethod.ROUTE_TAXI: "Маршруткой",
    OrderDeliveryMethod.CITY_DELIVERY: "Доставка по городу (Хасавюрт)",
    OrderDeliveryMethod.OZON: "Озон доставка",
    OrderDeliveryMethod.WB: "ВБ доставка",
    OrderDeliveryMethod.CDEK: "СДЭК",
}


def delivery_method_label(delivery_method: OrderDeliveryMethod | str | None) -> str | None:
    if delivery_method is None:
        return None
    try:
        normalized = OrderDeliveryMethod(delivery_method)
    except ValueError:
        return str(delivery_method)
    return ORDER_DELIVERY_METHOD_LABELS[normalized]
