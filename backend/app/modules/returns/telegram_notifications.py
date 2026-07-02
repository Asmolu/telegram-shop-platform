from __future__ import annotations

from collections.abc import Iterable

from app.core.config import join_public_url, settings
from app.db.models import ReturnRequestStatus

RETURN_CALLBACK_PREFIX = "return"
RETURN_APPROVE_COMMENT = "Одобрено через Telegram"
RETURN_REJECT_COMMENT = "Отклонено через Telegram"


def build_return_request_action_reply_markup(return_request_id: int) -> dict[str, object]:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Подтвердить",
                    "callback_data": f"{RETURN_CALLBACK_PREFIX}:approve:{return_request_id}",
                },
                {
                    "text": "Отклонить",
                    "callback_data": f"{RETURN_CALLBACK_PREFIX}:reject:{return_request_id}",
                },
            ]
        ]
    }


def build_return_request_notification_message(return_request: object) -> str:
    order = _attr(return_request, "order")
    user = _attr(return_request, "user")
    return_request_id = _attr(return_request, "id")
    order_id = _attr(return_request, "order_id")
    return_number = _text(_attr(return_request, "return_number")) or _id_label(
        return_request_id,
        prefix="#",
    )
    order_number = (
        _text(_attr(return_request, "order_number"))
        or _text(_attr(order, "order_number"))
        or _id_label(order_id, prefix="#")
    )
    customer_name = (
        _text(_attr(return_request, "customer_name"))
        or _text(_attr(order, "contact_name"))
        or _user_display_name(user)
        or _id_label(_attr(return_request, "user_id"), prefix="User #")
    )
    customer_phone = (
        _text(_attr(return_request, "customer_phone"))
        or _text(_attr(order, "contact_phone"))
        or _text(_attr(user, "phone"))
    )
    contact = f"{customer_name}, {customer_phone}" if customer_phone else customer_name
    items = sorted(
        _iterable(_attr(return_request, "items")),
        key=lambda item: _attr(item, "id") or 0,
    )
    item_lines = [_return_item_notification_line(item) for item in items]
    attachments = list(_iterable(_attr(return_request, "attachments")))
    seller_panel_url = join_public_url(
        settings.public_seller_panel_base_url,
        f"returns/{return_request_id}",
    )
    status_label = return_request_status_label(_attr(return_request, "status"))

    request_label = return_number
    if return_request_id is not None:
        request_label = f"{request_label} (ID {return_request_id})"
    order_label = order_number
    if order_id is not None:
        order_label = f"{order_label} (ID {order_id})"

    lines = [
        "Новая заявка на возврат",
        f"Статус: {status_label}",
        f"Заявка: {request_label}",
        f"Заказ: {order_label}",
        f"Клиент: {contact}",
        f"Причина: {_attr(return_request, 'reason')}",
    ]
    comment = _text(_attr(return_request, "comment"))
    if comment:
        lines.append(f"Комментарий: {comment}")
    lines.extend(
        [
            "Позиции:",
            *(item_lines or ["- нет позиций"]),
            f"Вложений: {len(attachments)}",
            f"Панель продавца: {seller_panel_url}",
        ]
    )
    decision_actor = _decision_actor_label(return_request)
    if decision_actor is not None:
        lines.append(f"Решил: {decision_actor}")
    decision_comment = _text(_attr(return_request, "decision_comment"))
    if decision_comment:
        lines.append(f"Комментарий решения: {decision_comment}")
    return "\n".join(lines)


def build_return_attachment_caption(return_request: object) -> str:
    return_number = _text(_attr(return_request, "return_number")) or _id_label(
        _attr(return_request, "id"),
        prefix="",
    )
    return f"Вложение к возврату #{return_number}"


def return_request_status_label(status: object) -> str:
    status_value = getattr(status, "value", status)
    if status_value == ReturnRequestStatus.APPROVED.value:
        return "Одобрено"
    if status_value == ReturnRequestStatus.REJECTED.value:
        return "Отклонено"
    return "Ожидает решения"


def _return_item_notification_line(item: object) -> str:
    details = [
        part
        for part in (
            _text(_attr(item, "product_brand")),
            _text(_attr(item, "sku")),
            _text(_attr(item, "size")),
            _text(_attr(item, "color")),
        )
        if part
    ]
    suffix = f" ({', '.join(details)})" if details else ""
    return f"- {_attr(item, 'product_name')}{suffix} x{_attr(item, 'quantity')}"


def _decision_actor_label(return_request: object) -> str | None:
    decided_by = _attr(return_request, "decided_by")
    actor_name = _user_display_name(decided_by)
    if actor_name:
        actor_id = _attr(decided_by, "id")
        return f"{actor_name} (ID {actor_id})" if actor_id is not None else actor_name
    decided_by_user_id = _attr(return_request, "decided_by_user_id")
    if decided_by_user_id is None:
        return None
    return f"пользователь #{decided_by_user_id}"


def _user_display_name(user: object | None) -> str | None:
    if user is None:
        return None
    parts = [
        _text(_attr(user, "first_name")),
        _text(_attr(user, "last_name")),
    ]
    name = " ".join(part for part in parts if part)
    if name:
        return name
    username = _text(_attr(user, "username")) or _text(_attr(user, "telegram_username"))
    return f"@{username}" if username else None


def _iterable(value: object) -> Iterable[object]:
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return value
    return ()


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _id_label(value: object, *, prefix: str) -> str:
    return f"{prefix}{value}" if value is not None else "—"


def _attr(value: object, name: str) -> object:
    if value is None:
        return None
    return getattr(value, name, None)
