import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.db.models import ManualPaymentStatus, OrderDeliveryMethod, OrderStatus

DISPLAY_TIMEZONE = ZoneInfo("Europe/Moscow")
MISSING_VALUE = "—"

ORDER_STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.NEW: "Новый",
    OrderStatus.PROCESSING: "В обработке",
    OrderStatus.SHIPPED: "Отправлен",
    OrderStatus.DELIVERED: "Доставлен",
    OrderStatus.CANCELLED: "Отменён",
}

PAYMENT_STATUS_LABELS: dict[ManualPaymentStatus, str] = {
    ManualPaymentStatus.PENDING: "Ожидает оплату",
    ManualPaymentStatus.SUBMITTED: "Оплата на проверке",
    ManualPaymentStatus.APPROVED: "Оплачено",
    ManualPaymentStatus.REJECTED: "Отклонено",
    ManualPaymentStatus.EXPIRED: "Время оплаты истекло",
    ManualPaymentStatus.CANCELLED: "Отменено",
}

DELIVERY_METHOD_LABELS: dict[OrderDeliveryMethod, str] = {
    OrderDeliveryMethod.ROUTE_TAXI: "Маршруткой",
    OrderDeliveryMethod.CITY_DELIVERY: "Доставка по городу (Хасавюрт)",
    OrderDeliveryMethod.OZON: "Ozon доставка",
    OrderDeliveryMethod.WB: "WB доставка",
    OrderDeliveryMethod.CDEK: "СДЭК",
}

BACKUP_STATUS_LABELS = {
    "success": "успешно",
    "failed": "ошибка",
    "warning_local_verified_only": "создана локально, удалённая загрузка не выполнена",
}

BACKUP_RESTORE_STATUS_LABELS = {
    "passed": "пройдена",
    "failed": "не пройдена",
    "pending": "ожидается",
    "not_run": "не выполнялась",
}


def order_status_label(value: OrderStatus | str | None) -> str:
    return _enum_label(value, OrderStatus, ORDER_STATUS_LABELS)


def payment_status_label(value: ManualPaymentStatus | str | None) -> str:
    return _enum_label(value, ManualPaymentStatus, PAYMENT_STATUS_LABELS)


def delivery_method_label(value: OrderDeliveryMethod | str | None) -> str:
    return _enum_label(value, OrderDeliveryMethod, DELIVERY_METHOD_LABELS)


def backup_status_label(value: str | None) -> str:
    if not value:
        return MISSING_VALUE
    return BACKUP_STATUS_LABELS.get(value, value)


def backup_restore_status_label(value: str | None) -> str:
    if not value:
        return MISSING_VALUE
    return BACKUP_RESTORE_STATUS_LABELS.get(value, value)


def backup_retention_label(value: str | None) -> str:
    if not value:
        return MISSING_VALUE
    match = re.fullmatch(r"deleted (\d+) (local|remote) archive\(s\)", value)
    if match:
        return f"удалено {match.group(1)} архив(ов)"
    return {
        "not_run": "не выполнялась",
        "skipped": "пропущена",
    }.get(value, value)


def format_rubles(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return MISSING_VALUE
    normalized = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    if normalized.endswith(",00"):
        normalized = normalized[:-3]
    return f"{normalized} ₽"


def format_datetime_moscow(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value or MISSING_VALUE
    else:
        return MISSING_VALUE
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=DISPLAY_TIMEZONE)
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%d.%m.%Y %H:%M")


def _enum_label(value, enum_type, labels: dict) -> str:
    if value is None or value == "":
        return MISSING_VALUE
    try:
        normalized = enum_type(value)
    except ValueError:
        return str(value)
    return labels[normalized]
