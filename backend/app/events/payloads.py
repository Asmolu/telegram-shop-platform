from decimal import Decimal
from typing import Any

from app.core.config import join_public_url, settings
from app.db.models import Order, OrderItem, OrderStatus, ProductImage
from app.modules.orders.delivery import delivery_method_label


def order_created_payload(order: Order) -> dict[str, object]:
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "status": order.status.value,
        "payment_status": (
            order.manual_payment.status.value if order.manual_payment is not None else None
        ),
        "created_at": _datetime(order.created_at),
        "user_id": order.user_id,
        "customer": _customer_payload(order),
        "items": [_order_item_payload(item) for item in order.items],
        "subtotal_amount": _money(order.subtotal_amount),
        "discount_amount": _money(order.discount_amount),
        "total_amount": _money(order.total_amount),
        "promo_code_id": order.promo_code_id,
        "promo_code": order.promo_code_code,
        "contact": {
            "name": order.contact_name,
            "phone": order.contact_phone,
            "delivery_method": (
                order.delivery_method.value if order.delivery_method is not None else None
            ),
            "delivery_method_label": delivery_method_label(order.delivery_method),
            "delivery_address": order.delivery_address,
            "delivery_comment": order.delivery_comment,
        },
        "seller_panel_url": _seller_panel_orders_url(),
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


def _datetime(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _customer_payload(order: Order) -> dict[str, object | None]:
    user = getattr(order, "user", None)
    if user is None:
        return {
            "user_id": order.user_id,
            "telegram_id": None,
            "username": None,
            "first_name": None,
            "last_name": None,
            "name": None,
        }
    name = " ".join(part for part in (user.first_name, user.last_name) if part) or None
    return {
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "name": name,
    }


def _order_item_payload(item: OrderItem) -> dict[str, object | None]:
    image = _primary_or_first_image(item.product.images if item.product is not None else [])
    image_url = _absolute_upload_url(image.url) if image is not None else None
    return {
        "product_id": item.product_id,
        "product_title": item.product_name,
        "product_link": _mini_app_product_url(item.product_id),
        "product_image_url": image_url,
        "variant_id": item.product_variant_id,
        "variant_size": item.variant_size,
        "variant_size_grid": item.variant_size_grid.value,
        "variant_color": item.variant_color,
        "variant_sku": item.variant_sku,
        "quantity": item.quantity,
        "unit_price": _money(item.unit_price),
        "item_total": _money(item.subtotal),
    }


def _primary_or_first_image(images: list[ProductImage]) -> ProductImage | None:
    if not images:
        return None
    primary = next((image for image in images if image.is_primary), None)
    return primary or images[0]


def _absolute_upload_url(url: str | None) -> str | None:
    if not url:
        return None
    return settings.public_upload_url_for(url)


def _mini_app_product_url(product_id: int) -> str:
    return join_public_url(settings.public_mini_app_base_url, f"product/{product_id}")


def _seller_panel_orders_url() -> str:
    return join_public_url(settings.public_seller_panel_base_url, "orders")
