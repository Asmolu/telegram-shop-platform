import html
from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi import status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.labels import (
    MISSING_VALUE,
    format_datetime_moscow,
    format_rubles,
    order_status_label,
    payment_status_label,
)
from app.common.pagination import PageMeta
from app.core.config import join_public_url, settings
from app.core.errors import AppError
from app.db.models import Notification, NotificationChannel, NotificationStatus
from app.events.names import ORDER_CREATED, ORDER_SHIPPED, ORDER_STATUS_CHANGED, PROMO_USED
from app.modules.notifications.repository import NotificationsRepository
from app.modules.notifications.schemas import NotificationList, NotificationRead
from app.modules.products.size_grids import format_size_for_display
from app.modules.telegram.service import TelegramDeliveryError, TelegramService

TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_PHOTO_CAPTION_LIMIT = 1024


class NotificationsEventPublisher:
    """Post-commit event adapter for notification creation."""

    def __init__(
        self,
        session: AsyncSession,
        notifications_service: "NotificationsService | None" = None,
    ) -> None:
        self.notifications_service = notifications_service or NotificationsService(session)

    async def emit(self, name: str, payload: Mapping[str, object]) -> None:
        await self.notifications_service.create_for_event(name=name, payload=payload)


class NotificationsService:
    """Notification persistence and delivery business logic."""

    def __init__(
        self,
        session: AsyncSession,
        telegram_service: TelegramService | None = None,
    ) -> None:
        self.session = session
        self.repository = NotificationsRepository(session)
        self.telegram_service = telegram_service or TelegramService()

    async def list_notifications(
        self,
        *,
        limit: int,
        offset: int,
        channel: NotificationChannel | None = None,
        status: NotificationStatus | None = None,
    ) -> NotificationList:
        items, total = await self.repository.list(
            limit=limit,
            offset=offset,
            channel=channel,
            status=status,
        )
        return NotificationList(
            items=[NotificationRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def list_user_notifications(
        self,
        *,
        user_id: int,
        limit: int,
        offset: int,
    ) -> NotificationList:
        items, total = await self.repository.list(limit=limit, offset=offset, user_id=user_id)
        return NotificationList(
            items=[NotificationRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_notification(self, notification_id: int) -> NotificationRead:
        notification = await self._get_existing_notification(notification_id)
        return NotificationRead.model_validate(notification)

    async def retry_notification(self, notification_id: int) -> NotificationRead:
        notification = await self._get_existing_notification(notification_id)
        if notification.status != NotificationStatus.FAILED:
            raise AppError("Only failed notifications can be retried", status.HTTP_400_BAD_REQUEST)
        if notification.channel != NotificationChannel.TELEGRAM:
            raise AppError(
                "Only Telegram notifications can be retried",
                status.HTTP_400_BAD_REQUEST,
            )

        notification.status = NotificationStatus.PENDING
        notification.error_message = None
        notification.sent_at = None
        await self._commit("Notification retry failed")
        await self._deliver_telegram(notification)
        return NotificationRead.model_validate(notification)

    async def create_for_event(
        self,
        *,
        name: str,
        payload: Mapping[str, object],
    ) -> NotificationRead | None:
        if name == ORDER_CREATED:
            return await self._create_order_created(payload)
        if name == ORDER_STATUS_CHANGED:
            return await self._create_order_status_changed(payload)
        if name == ORDER_SHIPPED:
            return await self._create_order_shipped(payload)
        if name == PROMO_USED:
            return await self._create_promo_used(payload)
        return None

    async def create_notification(
        self,
        *,
        type: str,
        title: str,
        message: str,
        payload: Mapping[str, object] | None,
        channel: NotificationChannel,
        user_id: int | None = None,
    ) -> Notification:
        sent_at = self._now() if channel == NotificationChannel.INTERNAL else None
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            payload=self._encode_payload(payload),
            channel=channel,
            status=(
                NotificationStatus.SENT
                if channel == NotificationChannel.INTERNAL
                else NotificationStatus.PENDING
            ),
            sent_at=sent_at,
        )
        self.repository.add(notification)
        await self._commit("Notification creation failed")
        await self.session.refresh(notification)
        return notification

    async def send_seller_telegram_message(
        self,
        *,
        type: str,
        title: str,
        message: str,
        payload: Mapping[str, object] | None = None,
    ) -> NotificationRead:
        notification = await self.create_notification(
            type=type,
            title=title,
            message=message,
            payload=payload,
            channel=NotificationChannel.TELEGRAM,
        )
        await self._deliver_telegram(notification)
        return NotificationRead.model_validate(notification)

    async def _create_order_created(self, payload: Mapping[str, object]) -> NotificationRead:
        order_number = self._order_label(payload)
        title = f"🛍 Новый заказ #{order_number}"
        message = self._format_seller_order_created_message(payload)
        notification = await self.create_notification(
            type=ORDER_CREATED,
            title=title,
            message=message,
            payload=payload,
            channel=NotificationChannel.TELEGRAM,
        )
        await self._deliver_telegram(notification)
        return NotificationRead.model_validate(notification)

    async def _create_order_status_changed(
        self,
        payload: Mapping[str, object],
    ) -> NotificationRead:
        order_number = self._order_label(payload)
        previous_status = self._payload_value(payload, "previous_status", fallback="")
        new_status = self._payload_value(payload, "new_status", fallback="")
        title = "🔄 Статус заказа изменён"
        message = (
            f"Заказ: {order_number}\n"
            f"Было: {order_status_label(previous_status)}\n"
            f"Стало: {order_status_label(new_status)}"
        )
        notification = await self.create_notification(
            type=ORDER_STATUS_CHANGED,
            title=title,
            message=message,
            payload=payload,
            channel=NotificationChannel.TELEGRAM,
        )
        await self._deliver_telegram(notification)
        return NotificationRead.model_validate(notification)

    async def _create_order_shipped(self, payload: Mapping[str, object]) -> NotificationRead:
        order_number = self._order_label(payload)
        user_id = self._payload_int(payload, "user_id")
        notification = await self.create_notification(
            user_id=user_id,
            type=ORDER_SHIPPED,
            title="Order shipped",
            message=f"Order {order_number} was shipped.",
            payload=payload,
            channel=NotificationChannel.INTERNAL,
        )
        return NotificationRead.model_validate(notification)

    async def _create_promo_used(self, payload: Mapping[str, object]) -> NotificationRead:
        promo_code = self._payload_value(payload, "promo_code", fallback="promo code")
        user_id = self._payload_int(payload, "user_id")
        order_number = self._order_label(payload)
        notification = await self.create_notification(
            user_id=user_id,
            type=PROMO_USED,
            title="Promo code used",
            message=f"Promo code {promo_code} was used on order {order_number}.",
            payload=payload,
            channel=NotificationChannel.INTERNAL,
        )
        return NotificationRead.model_validate(notification)

    async def _deliver_telegram(self, notification: Notification) -> None:
        try:
            await self._send_seller_telegram_notification(notification)
        except TelegramDeliveryError as exc:
            notification.status = NotificationStatus.FAILED
            notification.error_message = str(exc)
            notification.sent_at = None
        else:
            notification.status = NotificationStatus.SENT
            notification.error_message = None
            notification.sent_at = self._now()

        await self._commit("Notification delivery update failed")
        await self.session.refresh(notification)

    def _format_telegram_message(self, notification: Notification) -> str:
        if notification.type == ORDER_CREATED:
            title = html.escape(notification.title)
            message = html.escape(notification.message)
            return f"<b>{title}</b>\n\n{message}"
        return f"{notification.title}\n\n{notification.message}"

    async def _send_seller_telegram_notification(self, notification: Notification) -> None:
        message = self._format_telegram_message(notification)
        parts = self._split_telegram_message(message)
        image_url = self._first_product_image_url(notification.payload)
        parse_mode = "HTML" if notification.type == ORDER_CREATED else None
        if (
            notification.type == ORDER_CREATED
            and image_url is not None
            and len(parts) == 1
            and len(parts[0]) <= TELEGRAM_PHOTO_CAPTION_LIMIT
            and hasattr(self.telegram_service, "send_seller_photo")
        ):
            await self.telegram_service.send_seller_photo(
                image_url,
                caption=parts[0],
                parse_mode=parse_mode,
            )
            return

        for part in parts:
            await self.telegram_service.send_seller_notification(
                part,
                parse_mode=parse_mode,
            )

    def _format_seller_order_created_message(self, payload: Mapping[str, object]) -> str:
        order_id = self._payload_value(payload, "order_id", fallback=MISSING_VALUE)
        status_value = self._payload_value(payload, "status", fallback="")
        payment_status = self._payload_value(payload, "payment_status", fallback="")
        created_at = self._payload_value(payload, "created_at", fallback="")
        subtotal = self._payload_value(payload, "subtotal_amount", fallback="0.00")
        discount = self._payload_value(payload, "discount_amount", fallback="0.00")
        delivery_price = self._payload_value(payload, "delivery_price", fallback="0.00")
        total = self._payload_value(payload, "total_amount", fallback="0.00")
        promo = self._payload_value(payload, "promo_code", fallback=MISSING_VALUE)
        seller_panel_url = self._payload_value(
            payload,
            "seller_panel_url",
            fallback=_seller_panel_orders_url(),
        )

        lines = [
            f"ID заказа: {order_id}",
            f"Статус: {order_status_label(status_value)}",
            f"Оплата: {payment_status_label(payment_status)}",
            f"Создан: {format_datetime_moscow(created_at)}",
            "",
            "Клиент",
            *self._customer_lines(payload.get("customer")),
            "",
            "Товары",
            *self._product_lines(payload.get("items")),
            "",
            "Сумма",
            f"Товары: {format_rubles(subtotal)}",
            f"Промокод: {promo or MISSING_VALUE}",
            f"Скидка: {format_rubles(discount)}",
            f"Доставка: {format_rubles(delivery_price)}",
            f"К оплате: {format_rubles(total)}",
            "",
            "Доставка и контакты",
            *self._contact_lines(payload.get("contact"), payload.get("customer")),
            "",
            f"Панель продавца: {seller_panel_url}",
        ]
        return "\n".join(lines)

    def _customer_lines(self, customer: object) -> list[str]:
        if not isinstance(customer, dict):
            return [MISSING_VALUE]
        username = customer.get("username")
        telegram_tag = f"@{username}" if username else MISSING_VALUE
        name = customer.get("name") or self._join_name(
            customer.get("first_name"),
            customer.get("last_name"),
        )
        return [
            f"Telegram: {telegram_tag}",
            f"Имя в Mini App: {name or MISSING_VALUE}",
            f"ID клиента: {customer.get('user_id') or MISSING_VALUE}",
            f"Telegram ID: {customer.get('telegram_id') or MISSING_VALUE}",
        ]

    def _product_lines(self, items: object) -> list[str]:
        if not isinstance(items, list) or not items:
            return [MISSING_VALUE]
        lines: list[str] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            size = item.get("variant_size")
            size_grid = item.get("variant_size_grid") or "clothing_alpha"
            try:
                display_size = (
                    format_size_for_display(str(size_grid), str(size))
                    if size
                    else MISSING_VALUE
                )
            except ValueError:
                display_size = str(size) if size else MISSING_VALUE
            lines.extend(
                [
                    f"{index}) {item.get('product_title') or MISSING_VALUE}",
                    f"   ID товара: {item.get('product_id') or MISSING_VALUE}",
                    f"   Размер: {display_size}",
                    f"   Цвет: {item.get('variant_color') or MISSING_VALUE}",
                    f"   SKU: {item.get('variant_sku') or MISSING_VALUE}",
                    f"   Количество: {item.get('quantity') or MISSING_VALUE}",
                    f"   Цена: {format_rubles(item.get('unit_price') or '0.00')}",
                    f"   Итого: {format_rubles(item.get('item_total') or '0.00')}",
                    f"   Ссылка: {item.get('product_link') or MISSING_VALUE}",
                    f"   Фото: {item.get('product_image_url') or MISSING_VALUE}",
                ]
            )
        return lines or [MISSING_VALUE]

    def _contact_lines(self, contact: object, customer: object) -> list[str]:
        if not isinstance(contact, dict):
            return [MISSING_VALUE]
        username = customer.get("username") if isinstance(customer, dict) else None
        return [
            f"Способ доставки: {contact.get('delivery_method_label') or MISSING_VALUE}",
            f"Имя: {contact.get('name') or MISSING_VALUE}",
            f"Телефон: {contact.get('phone') or MISSING_VALUE}",
            f"Адрес: {contact.get('delivery_address') or MISSING_VALUE}",
            f"Комментарий: {contact.get('delivery_comment') or MISSING_VALUE}",
            f"Telegram: @{username}" if username else f"Telegram: {MISSING_VALUE}",
        ]

    def _split_telegram_message(
        self,
        message: str,
        *,
        limit: int = TELEGRAM_MESSAGE_LIMIT,
    ) -> list[str]:
        if len(message) <= limit:
            return [message]

        parts: list[str] = []
        current = ""
        for line in message.splitlines(keepends=True):
            if len(line) > limit:
                if current:
                    parts.append(current.rstrip())
                    current = ""
                parts.extend(line[index : index + limit] for index in range(0, len(line), limit))
                continue
            if len(current) + len(line) > limit:
                parts.append(current.rstrip())
                current = line
            else:
                current += line
        if current:
            parts.append(current.rstrip())
        return [part for part in parts if part]

    def _first_product_image_url(self, payload: Mapping[str, object] | None) -> str | None:
        if payload is None:
            return None
        items = payload.get("items")
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                continue
            image_url = item.get("product_image_url")
            if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
                return image_url
        return None

    def _join_name(self, first_name: object, last_name: object) -> str | None:
        parts = [part for part in (first_name, last_name) if isinstance(part, str) and part]
        return " ".join(parts) or None

    async def _get_existing_notification(self, notification_id: int) -> Notification:
        notification = await self.repository.get_by_id(notification_id)
        if notification is None:
            raise AppError("Notification not found", status.HTTP_404_NOT_FOUND)
        return notification

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc

    def _encode_payload(self, payload: Mapping[str, object] | None) -> dict[str, object] | None:
        if payload is None:
            return None
        encoded = jsonable_encoder(dict(payload))
        return encoded if isinstance(encoded, dict) else None

    def _payload_value(
        self,
        payload: Mapping[str, object],
        key: str,
        *,
        fallback: str,
    ) -> str:
        value = payload.get(key)
        if value is None:
            return fallback
        return str(value)

    def _order_label(self, payload: Mapping[str, object]) -> str:
        order_id = self._payload_value(payload, "order_id", fallback="unknown")
        return self._payload_value(payload, "order_number", fallback=f"#{order_id}")

    def _payload_int(self, payload: Mapping[str, object], key: str) -> int | None:
        value = payload.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _now(self) -> datetime:
        return datetime.now(UTC)


def _seller_panel_orders_url() -> str:
    return join_public_url(settings.public_seller_panel_base_url, "orders")
