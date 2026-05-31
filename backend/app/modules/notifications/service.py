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
        total_amount = self._payload_value(payload, "total_amount", fallback="0.00")
        title = f"New order {order_number}"
        message = f"Order {order_number} was created. Total: {total_amount}."
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
            await self.telegram_service.send_seller_notification(
                self._format_telegram_message(notification)
            )
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
