from decimal import Decimal

from app.db.models import Order, OrderStatus


def order_created_payload(order: Order) -> dict[str, object]:
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "user_id": order.user_id,
        "subtotal_amount": _money(order.subtotal_amount),
        "discount_amount": _money(order.discount_amount),
        "total_amount": _money(order.total_amount),
        "promo_code_id": order.promo_code_id,
        "promo_code": order.promo_code_code,
    }


def order_status_changed_payload(
    order: Order,
    *,
    previous_status: OrderStatus,
) -> dict[str, object]:
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "user_id": order.user_id,
        "previous_status": previous_status.value,
        "new_status": order.status.value,
    }


def order_shipped_payload(order: Order) -> dict[str, object]:
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "user_id": order.user_id,
        "status": order.status.value,
    }


def promo_used_payload(order: Order) -> dict[str, object]:
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "user_id": order.user_id,
        "promo_code_id": order.promo_code_id,
        "promo_code": order.promo_code_code,
        "discount_amount": _money(order.discount_amount),
    }


def _money(value: Decimal) -> str:
    return str(value)
