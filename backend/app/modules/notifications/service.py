from collections.abc import Mapping
from datetime import UTC, datetime

from fastapi import status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import Notification, NotificationChannel, NotificationStatus
from app.events.names import ORDER_CREATED, ORDER_SHIPPED, ORDER_STATUS_CHANGED, PROMO_USED
from app.modules.notifications.repository import NotificationsRepository
from app.modules.notifications.schemas import NotificationList, NotificationRead
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
        title = f"New order {order_number}"
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
        previous_status = self._payload_value(payload, "previous_status", fallback="unknown")
        new_status = self._payload_value(payload, "new_status", fallback="unknown")
        title = f"Order {order_number} status changed"
        message = f"Order {order_number} changed from {previous_status} to {new_status}."
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
        return f"{notification.title}\n\n{notification.message}"

    async def _send_seller_telegram_notification(self, notification: Notification) -> None:
        message = self._format_telegram_message(notification)
        parts = self._split_telegram_message(message)
        image_url = self._first_product_image_url(notification.payload)
        if (
            notification.type == ORDER_CREATED
            and image_url is not None
            and len(parts) == 1
            and len(parts[0]) <= TELEGRAM_PHOTO_CAPTION_LIMIT
            and hasattr(self.telegram_service, "send_seller_photo")
        ):
            await self.telegram_service.send_seller_photo(image_url, caption=parts[0])
            return

        for part in parts:
            await self.telegram_service.send_seller_notification(part)

    def _format_seller_order_created_message(self, payload: Mapping[str, object]) -> str:
        order_id = self._payload_value(payload, "order_id", fallback="unknown")
        order_number = self._order_label(payload)
        status_value = self._payload_value(payload, "status", fallback="unknown")
        created_at = self._payload_value(payload, "created_at", fallback="unknown")
        subtotal = self._payload_value(payload, "subtotal_amount", fallback="0.00")
        discount = self._payload_value(payload, "discount_amount", fallback="0.00")
        total = self._payload_value(payload, "total_amount", fallback="0.00")
        promo = self._payload_value(payload, "promo_code", fallback="-")
        seller_panel_url = self._payload_value(
            payload,
            "seller_panel_url",
            fallback="https://seller.tsplatform.ru/orders",
        )

        lines = [
            f"Order ID: {order_id}",
            f"Order number: {order_number}",
            f"Status: {status_value}",
            f"Created at: {created_at}",
            "",
            "Customer:",
            *self._customer_lines(payload.get("customer")),
            "",
            "Products:",
            *self._product_lines(payload.get("items")),
            "",
            "Totals:",
            f"Subtotal: {subtotal}",
            f"Promo code: {promo or '-'}",
            f"Discount: {discount}",
            f"Final total: {total}",
            "",
            "Delivery/contact:",
            *self._contact_lines(payload.get("contact")),
            "",
            f"Seller Panel: {seller_panel_url}",
        ]
        return "\n".join(lines)

    def _customer_lines(self, customer: object) -> list[str]:
        if not isinstance(customer, dict):
            return ["-"]
        username = customer.get("username")
        telegram_tag = f"@{username}" if username else "-"
        name = customer.get("name") or self._join_name(
            customer.get("first_name"),
            customer.get("last_name"),
        )
        return [
            f"Telegram: {telegram_tag}",
            f"Customer ID: {customer.get('user_id') or '-'}",
            f"Telegram ID: {customer.get('telegram_id') or '-'}",
            f"Mini App name: {name or '-'}",
        ]

    def _product_lines(self, items: object) -> list[str]:
        if not isinstance(items, list) or not items:
            return ["-"]
        lines: list[str] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            variant_parts = [
                f"size={item.get('variant_size') or '-'}",
                f"color={item.get('variant_color') or '-'}",
                f"sku={item.get('variant_sku') or '-'}",
            ]
            lines.extend(
                [
                    f"{index}. {item.get('product_title') or '-'}",
                    f"   Product ID: {item.get('product_id') or '-'}",
                    f"   Link: {item.get('product_link') or '-'}",
                    f"   Image: {item.get('product_image_url') or '-'}",
                    f"   Variant: {', '.join(variant_parts)}",
                    f"   Quantity: {item.get('quantity') or '-'}",
                    f"   Unit price: {item.get('unit_price') or '0.00'}",
                    f"   Item total: {item.get('item_total') or '0.00'}",
                ]
            )
        return lines or ["-"]

    def _contact_lines(self, contact: object) -> list[str]:
        if not isinstance(contact, dict):
            return ["-"]
        return [
            f"Name: {contact.get('name') or '-'}",
            f"Phone: {contact.get('phone') or '-'}",
            f"Address: {contact.get('delivery_address') or '-'}",
            f"Comment: {contact.get('delivery_comment') or '-'}",
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
