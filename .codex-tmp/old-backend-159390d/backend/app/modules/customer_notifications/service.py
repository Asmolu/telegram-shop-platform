from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.labels import order_status_label
from app.common.pagination import PageMeta
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    CustomerServiceNotificationDelivery,
    CustomerServiceNotificationDeliveryStatus,
    CustomerTelegramSubscription,
    NotificationChannel,
    OrderStatus,
    User,
)
from app.events.names import (
    MANUAL_PAYMENT_APPROVED,
    MANUAL_PAYMENT_APPROVED_CUSTOMER,
    MANUAL_PAYMENT_EXPIRED,
    MANUAL_PAYMENT_EXPIRED_CUSTOMER,
    MANUAL_PAYMENT_REJECTED,
    MANUAL_PAYMENT_REJECTED_CUSTOMER,
    ORDER_CANCELLED_CUSTOMER,
    ORDER_CREATED,
    ORDER_CREATED_CUSTOMER,
    ORDER_DELIVERED_CUSTOMER,
    ORDER_PROCESSING_CUSTOMER,
    ORDER_SHIPPED_CUSTOMER,
    ORDER_STATUS_CHANGED,
    ORDER_STATUS_CHANGED_CUSTOMER,
    SELLER_CUSTOMER_MESSAGE,
)
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.customer_notifications.repository import CustomerNotificationsRepository
from app.modules.customer_notifications.schemas import (
    CustomerBotWebhookResponse,
    CustomerOrderMessageRead,
    CustomerServiceNotificationDeliveryList,
    CustomerServiceNotificationDeliveryRead,
    CustomerSubscriptionAdminRead,
    CustomerSubscriptionList,
    CustomerSubscriptionMe,
    CustomerSubscriptionStartLink,
    CustomerSubscriptionUpdate,
    CustomerWriteAccessRequest,
)
from app.modules.orders.repository import OrdersRepository
from app.modules.telegram.schemas import TelegramCallbackQuery, TelegramMessage, TelegramUpdate
from app.modules.telegram.service import TelegramDeliveryError, TelegramService
from app.modules.uploads.service import UploadsService
from app.modules.users.repository import UsersRepository

logger = logging.getLogger(__name__)

START_COMMAND_RE = re.compile(
    r"^/start(?:@[A-Za-z0-9_]{5,32})?(?:\s+(?P<payload>\S+))?$",
    re.IGNORECASE,
)
COMMAND_RE = re.compile(r"^(?P<command>/[A-Za-z_]+)(?:@[A-Za-z0-9_]{5,32})?(?:\s+(?P<args>.*))?$")
PRIVATE_CHAT_TYPE = "private"
UNKNOWN_CHAT_TYPE = "unknown"
START_LINK_PAYLOAD = "notifications"
CALLBACK_PREFIX = "customer_notifications"
ACTION_SUBSCRIPTION_UPDATED = "customer_notifications.subscription_updated"
ACTION_CUSTOMER_ORDER_NOTIFICATION_SENT = "customer_order_notification_sent"
ACTION_CUSTOMER_ORDER_NOTIFICATION_FAILED = "customer_order_notification_failed"
TELEGRAM_ERROR_MESSAGE_MAX_LENGTH = 500

STOP_MESSAGE = "Уведомления выключены. Чтобы снова получать сообщения, отправьте /start."
CONNECT_PRIVATE_CHAT_MESSAGE = (
    "Уведомления можно подключить только в личном чате с ботом. Откройте бота и отправьте /start."
)
ORDER_CREATED_CUSTOMER_MESSAGE = "Заказ создан"
ORDER_STATUS_CHANGED_CUSTOMER_MESSAGE = "Статус заказа изменён"
ORDER_PROCESSING_CUSTOMER_MESSAGE = "Заказ принят в обработку"
ORDER_SHIPPED_CUSTOMER_MESSAGE = "Заказ отправлен"
ORDER_DELIVERED_CUSTOMER_MESSAGE = "Заказ доставлен"
ORDER_CANCELLED_CUSTOMER_MESSAGE = "Заказ отменён"


WELCOME_MESSAGE = "Уведомления подключены. Сообщения по заказам включены."


def has_active_private_chat(subscription: CustomerTelegramSubscription) -> bool:
    return (
        subscription.has_chat
        and subscription.telegram_chat_id is not None
        and subscription.chat_type == PRIVATE_CHAT_TYPE
        and subscription.blocked_at is None
    )


def resolve_customer_service_send_target(
    subscription: CustomerTelegramSubscription,
) -> int | None:
    if has_active_private_chat(subscription):
        return subscription.telegram_chat_id
    if bool(subscription.write_access_granted) and subscription.blocked_at is None:
        return subscription.telegram_user_id
    return None


class CustomerTelegramSender:
    """Bot 1 Telegram sender for customer-facing messages."""

    def __init__(self, telegram_service: TelegramService | None = None) -> None:
        self.telegram_service = telegram_service or TelegramService(
            bot_token=settings.telegram_customer_bot_token,
        )

    async def send_message(self, chat_id: int, message: str) -> int | None:
        return await self.telegram_service.send_message(str(chat_id), message)

    async def send_photo(
        self,
        chat_id: int,
        photo: bytes,
        *,
        filename: str,
        mime_type: str,
        caption: str | None = None,
    ) -> int | None:
        return await self.telegram_service.send_photo_bytes(
            str(chat_id),
            photo,
            filename=filename,
            mime_type=mime_type,
            caption=caption,
        )


class SellerCustomerOrderMessageService:
    """Seller/admin delivery of an order-specific Bot 1 message."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: CustomerNotificationsRepository | None = None,
        orders_repository: OrdersRepository | None = None,
        sender: CustomerTelegramSender | None = None,
        uploads_service: UploadsService | None = None,
        audit_service: AuditService | NoopAuditService | None = None,
        now_factory: Any | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or CustomerNotificationsRepository(session)
        self.orders_repository = orders_repository or OrdersRepository(session)
        self.sender = sender or CustomerTelegramSender()
        self.uploads_service = uploads_service or UploadsService(session)
        self.audit_service = audit_service or AuditService(session)
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    async def send(
        self,
        *,
        order_id: int,
        actor_user_id: int,
        text: str | None,
        photo: UploadFile | None,
    ) -> CustomerOrderMessageRead:
        clean_text = text.strip() if text else None
        if not clean_text and photo is None:
            raise AppError(
                "Введите текст или выберите фотографию",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if photo is None and clean_text and len(clean_text) > 4096:
            raise AppError(
                "Текст сообщения не должен превышать 4096 символов",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )
        if photo is not None and clean_text and len(clean_text) > 1024:
            raise AppError(
                "Подпись к фотографии не должна превышать 1024 символа",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        order = await self.orders_repository.get_by_id(order_id)
        if order is None:
            raise AppError("Заказ не найден", status.HTTP_404_NOT_FOUND)
        subscription = await self.repository.get_by_user_id(order.user_id)
        unavailable = self._unavailable_reason(subscription, user_id=order.user_id)

        delivery = CustomerServiceNotificationDelivery(
            user_id=order.user_id,
            order_id=order.id,
            subscription_id=subscription.id if subscription is not None else None,
            event_name=SELLER_CUSTOMER_MESSAGE,
            channel=NotificationChannel.TELEGRAM,
            status=CustomerServiceNotificationDeliveryStatus.PENDING,
        )
        if unavailable is not None:
            error_code, error_message = unavailable
            delivery.status = CustomerServiceNotificationDeliveryStatus.SKIPPED
            delivery.error_code = error_code
            delivery.error_message = error_message
            self.repository.add_delivery(delivery)
            await self._flush_if_supported()
            await self._audit(delivery, actor_user_id=actor_user_id)
            await self._commit("Не удалось записать попытку отправки сообщения")
            raise AppError(error_message, status.HTTP_409_CONFLICT)

        validated_photo = None
        if photo is not None:
            validated_photo = await self.uploads_service.validate_and_read_image(photo)

        self.repository.add_delivery(delivery)
        await self._commit("Не удалось создать попытку отправки сообщения")

        assert subscription is not None
        send_target = resolve_customer_service_send_target(subscription)
        assert send_target is not None
        try:
            if validated_photo is not None:
                telegram_message_id = await self.sender.send_photo(
                    send_target,
                    validated_photo.content,
                    filename=validated_photo.original_filename,
                    mime_type=validated_photo.mime_type,
                    caption=clean_text,
                )
            else:
                assert clean_text is not None
                telegram_message_id = await self.sender.send_message(
                    send_target,
                    clean_text,
                )
        except TelegramDeliveryError as exc:
            self._mark_failed(delivery, subscription, exc)
            await self._audit(delivery, actor_user_id=actor_user_id)
            await self._commit("Не удалось сохранить ошибку отправки сообщения")
            raise AppError(
                self._seller_error_message(delivery),
                status.HTTP_502_BAD_GATEWAY,
            ) from exc

        delivery.status = CustomerServiceNotificationDeliveryStatus.SENT
        delivery.telegram_message_id = telegram_message_id
        delivery.error_code = None
        delivery.error_message = None
        delivery.sent_at = self.now_factory()
        subscription.last_delivery_error = None
        await self._audit(delivery, actor_user_id=actor_user_id)
        await self._commit("Не удалось сохранить результат отправки сообщения")
        return CustomerOrderMessageRead(
            order_id=order.id,
            delivery_id=delivery.id,
            telegram_message_id=telegram_message_id,
            sent_text=bool(clean_text),
            sent_photo=validated_photo is not None,
        )

    def _unavailable_reason(
        self,
        subscription: CustomerTelegramSubscription | None,
        *,
        user_id: int,
    ) -> tuple[str, str] | None:
        if subscription is None or subscription.user_id != user_id:
            return (
                "subscription_missing",
                "Покупатель не открыл Bot 1. Отправка сообщения недоступна.",
            )
        if subscription.blocked_at is not None:
            return ("subscription_blocked", "Покупатель заблокировал Bot 1.")
        if resolve_customer_service_send_target(subscription) is None:
            if subscription.write_access_denied_at is not None:
                return (
                    "write_access_denied",
                    "Покупатель не разрешил Bot 1 отправлять уведомления о заказах.",
                )
            return (
                "chat_unavailable",
                "У покупателя нет активного личного чата с Bot 1.",
            )
        if not subscription.service_opt_in:
            return (
                "service_opt_out",
                "Покупатель отключил сервисные сообщения Bot 1.",
            )
        return None

    def _mark_failed(
        self,
        delivery: CustomerServiceNotificationDelivery,
        subscription: CustomerTelegramSubscription,
        error: TelegramDeliveryError,
    ) -> None:
        error_code = self._delivery_error_code(error)
        delivery.status = (
            CustomerServiceNotificationDeliveryStatus.BLOCKED
            if error_code == "blocked"
            else CustomerServiceNotificationDeliveryStatus.FAILED
        )
        delivery.error_code = error_code
        delivery.error_message = self._sanitize_error_message(error)
        delivery.retry_after_seconds = error.retry_after_seconds
        if error_code == "blocked":
            subscription.blocked_at = self.now_factory()
            subscription.has_chat = False
        subscription.last_delivery_error = delivery.error_message

    def _delivery_error_code(self, error: TelegramDeliveryError) -> str:
        message = str(error).lower()
        if (
            error.status_code == status.HTTP_403_FORBIDDEN
            or str(error.error_code) == "403"
            or "forbidden" in message
            or "blocked" in message
        ):
            return "blocked"
        if (
            error.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            or str(error.error_code) == "429"
            or error.retry_after_seconds is not None
        ):
            return "rate_limited"
        return "telegram_error"

    def _sanitize_error_message(self, error: TelegramDeliveryError) -> str:
        message = " ".join((str(error) or "Telegram delivery failed").split())
        for secret in (settings.telegram_customer_bot_token, settings.telegram_bot_token):
            if secret:
                message = message.replace(secret, "[redacted]")
        return message[:TELEGRAM_ERROR_MESSAGE_MAX_LENGTH]

    def _seller_error_message(
        self,
        delivery: CustomerServiceNotificationDelivery,
    ) -> str:
        if delivery.error_code == "blocked":
            return "Покупатель заблокировал Bot 1. Сообщение не отправлено."
        if delivery.error_code == "rate_limited":
            return "Telegram временно ограничил отправку. Повторите попытку позже."
        return "Bot 1 не смог доставить сообщение. Повторите попытку позже."

    async def _audit(
        self,
        delivery: CustomerServiceNotificationDelivery,
        *,
        actor_user_id: int,
    ) -> None:
        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action=(
                "seller_customer_message_sent"
                if delivery.status == CustomerServiceNotificationDeliveryStatus.SENT
                else "seller_customer_message_failed"
            ),
            entity_type="customer_service_notification_delivery",
            entity_id=delivery.id,
            after_data={
                "order_id": delivery.order_id,
                "user_id": delivery.user_id,
                "status": delivery.status.value,
                "error_code": delivery.error_code,
            },
            metadata={"bot": "customer_bot_1"},
            commit=False,
        )

    async def _flush_if_supported(self) -> None:
        flush = getattr(self.session, "flush", None)
        if callable(flush):
            await flush()

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc


class CustomerServiceNotificationDeliveryService:
    """Customer service notification delivery boundary for Bot 1."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: CustomerNotificationsRepository | None = None,
        sender: CustomerTelegramSender | None = None,
        audit_service: AuditService | NoopAuditService | None = None,
        now_factory: Any | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or CustomerNotificationsRepository(session)
        self.sender = sender or CustomerTelegramSender()
        self.audit_service = audit_service or (
            AuditService(session) if hasattr(session, "add") else NoopAuditService()
        )
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    async def handle_order_event(
        self,
        name: str,
        payload: Mapping[str, object],
        source_event_id: UUID | None = None,
        source_consumer: str | None = None,
    ) -> CustomerServiceNotificationDelivery | None:
        if name == ORDER_CREATED:
            return await self.notify_order_created(payload, source_event_id, source_consumer)
        if name == ORDER_STATUS_CHANGED:
            return await self.notify_order_status_changed(payload, source_event_id, source_consumer)
        if name in {
            MANUAL_PAYMENT_APPROVED,
            MANUAL_PAYMENT_REJECTED,
            MANUAL_PAYMENT_EXPIRED,
        }:
            return await self.notify_manual_payment(name, payload, source_event_id, source_consumer)
        return None

    async def notify_order_created(
        self,
        payload: Mapping[str, object],
        source_event_id: UUID | None = None,
        source_consumer: str | None = None,
    ) -> CustomerServiceNotificationDelivery | None:
        user_id = self._payload_int(payload, "user_id")
        if user_id is None:
            return None
        return await self._deliver_service_notification(
            user_id=user_id,
            order_id=self._payload_int(payload, "order_id"),
            event_name=ORDER_CREATED_CUSTOMER,
            message=self._order_created_message(payload),
            source_event_id=source_event_id,
            source_consumer=source_consumer,
        )

    async def notify_order_status_changed(
        self,
        payload: Mapping[str, object],
        source_event_id: UUID | None = None,
        source_consumer: str | None = None,
    ) -> CustomerServiceNotificationDelivery | None:
        user_id = self._payload_int(payload, "user_id")
        if user_id is None:
            return None

        event_name, message = self._status_event_and_message(payload)
        return await self._deliver_service_notification(
            user_id=user_id,
            order_id=self._payload_int(payload, "order_id"),
            event_name=event_name,
            message=message,
            source_event_id=source_event_id,
            source_consumer=source_consumer,
        )

    async def notify_manual_payment(
        self,
        name: str,
        payload: Mapping[str, object],
        source_event_id: UUID | None = None,
        source_consumer: str | None = None,
    ) -> CustomerServiceNotificationDelivery | None:
        user_id = self._payload_int(payload, "user_id")
        if user_id is None:
            return None

        order_label = self._order_label(payload)
        if name == MANUAL_PAYMENT_APPROVED:
            event_name = MANUAL_PAYMENT_APPROVED_CUSTOMER
            message = f"Оплата подтверждена\n\nЗаказ {order_label} принят в обработку."
        elif name == MANUAL_PAYMENT_REJECTED:
            event_name = MANUAL_PAYMENT_REJECTED_CUSTOMER
            reason = self._payload_value(
                payload,
                "reject_reason",
                fallback="причина не указана",
            )
            message = (
                f"Оплата отклонена\n\nЗаказ {order_label}. Причина: {reason}. Резерв товара снят."
            )
        else:
            event_name = MANUAL_PAYMENT_EXPIRED_CUSTOMER
            message = f"Время оплаты истекло\n\nЗаказ {order_label} отменен. Резерв товара снят."

        return await self._deliver_service_notification(
            user_id=user_id,
            order_id=self._payload_int(payload, "order_id"),
            event_name=event_name,
            message=message,
            source_event_id=source_event_id,
            source_consumer=source_consumer,
        )

    async def _deliver_service_notification(
        self,
        *,
        user_id: int,
        order_id: int | None,
        event_name: str,
        message: str,
        source_event_id: UUID | None = None,
        source_consumer: str | None = None,
    ) -> CustomerServiceNotificationDelivery:
        subscription = await self.repository.get_by_user_id(user_id)
        delivery = (
            await self.repository.get_delivery_by_source(
                event_id=source_event_id, consumer=source_consumer
            )
            if source_event_id is not None and source_consumer is not None
            else None
        )
        if delivery is not None and delivery.status in {
            CustomerServiceNotificationDeliveryStatus.SENT,
            CustomerServiceNotificationDeliveryStatus.SKIPPED,
            CustomerServiceNotificationDeliveryStatus.BLOCKED,
        }:
            return delivery
        is_new = delivery is None
        delivery = delivery or CustomerServiceNotificationDelivery(
            user_id=user_id,
            order_id=order_id,
            subscription_id=subscription.id if subscription is not None else None,
            event_name=event_name,
            channel=NotificationChannel.TELEGRAM,
            status=CustomerServiceNotificationDeliveryStatus.PENDING,
            source_event_id=source_event_id,
            source_consumer=source_consumer,
        )

        skip_reason = self._skip_reason(subscription, user_id=user_id)
        if skip_reason is not None:
            error_code, error_message = skip_reason
            delivery.status = CustomerServiceNotificationDeliveryStatus.SKIPPED
            delivery.error_code = error_code
            delivery.error_message = error_message
            if is_new:
                self.repository.add_delivery(delivery)
            await self._flush_if_supported()
            await self._audit_delivery(delivery, action=ACTION_CUSTOMER_ORDER_NOTIFICATION_FAILED)
            await self._commit("Customer service notification skip recording failed")
            return delivery

        if is_new:
            self.repository.add_delivery(delivery)
            await self._commit("Customer service notification delivery creation failed")
        else:
            await self._commit("Customer service notification pre-send commit failed")

        assert subscription is not None
        send_target = resolve_customer_service_send_target(subscription)
        assert send_target is not None
        try:
            telegram_message_id = await self.sender.send_message(
                send_target,
                message,
            )
        except TelegramDeliveryError as exc:
            self._mark_delivery_failed(
                delivery=delivery,
                subscription=subscription,
                error=exc,
            )
        else:
            delivery.status = CustomerServiceNotificationDeliveryStatus.SENT
            delivery.telegram_message_id = telegram_message_id
            delivery.error_code = None
            delivery.error_message = None
            delivery.retry_after_seconds = None
            delivery.sent_at = self._now()
            subscription.last_delivery_error = None

        action = (
            ACTION_CUSTOMER_ORDER_NOTIFICATION_SENT
            if delivery.status == CustomerServiceNotificationDeliveryStatus.SENT
            else ACTION_CUSTOMER_ORDER_NOTIFICATION_FAILED
        )
        await self._audit_delivery(delivery, action=action)
        await self._commit("Customer service notification delivery update failed")
        return delivery

    def _skip_reason(
        self,
        subscription: CustomerTelegramSubscription | None,
        *,
        user_id: int,
    ) -> tuple[str, str] | None:
        if subscription is None:
            return "subscription_missing", "Customer Bot 1 subscription is missing"
        if subscription.user_id != user_id:
            return "subscription_user_mismatch", "Subscription is not linked to order user"
        if subscription.blocked_at is not None:
            return "subscription_blocked", "Customer Bot 1 chat is blocked"
        if resolve_customer_service_send_target(subscription) is None:
            if subscription.write_access_denied_at is not None:
                return "write_access_denied", "Customer denied Bot 1 write access"
            if subscription.has_chat and subscription.telegram_chat_id is None:
                return "chat_missing", "Customer Bot 1 chat id is missing"
            if subscription.has_chat and subscription.chat_type != PRIVATE_CHAT_TYPE:
                return "non_private_chat", "Customer Bot 1 chat is not private"
            return "chat_unavailable", "Customer Bot 1 private chat or write access is unavailable"
        if not subscription.service_opt_in:
            return "service_opt_out", "Customer opted out of service notifications"
        return None

    def _mark_delivery_failed(
        self,
        *,
        delivery: CustomerServiceNotificationDelivery,
        subscription: CustomerTelegramSubscription,
        error: TelegramDeliveryError,
    ) -> None:
        now = self._now()
        error_code = self._delivery_error_code(error)
        error_message = self._sanitize_error_message(error)
        delivery.status = (
            CustomerServiceNotificationDeliveryStatus.BLOCKED
            if error_code == "blocked"
            else CustomerServiceNotificationDeliveryStatus.FAILED
        )
        delivery.error_code = error_code
        delivery.error_message = error_message
        delivery.retry_after_seconds = error.retry_after_seconds
        delivery.sent_at = None
        subscription.last_delivery_error = error_message

        if error_code == "blocked":
            subscription.blocked_at = now
            subscription.has_chat = False

    def _delivery_error_code(self, error: TelegramDeliveryError) -> str:
        message = str(error).lower()
        if (
            error.status_code == status.HTTP_403_FORBIDDEN
            or str(error.error_code) == "403"
            or "forbidden" in message
            or "blocked" in message
        ):
            return "blocked"
        if (
            error.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            or str(error.error_code) == "429"
            or error.retry_after_seconds is not None
            or "too many requests" in message
            or "retry after" in message
        ):
            return "rate_limited"
        if "token is not configured" in message:
            return "configuration_error"
        if error.status_code is not None:
            return f"telegram_http_{error.status_code}"
        if error.error_code is not None:
            return self._sanitize_error_code(str(error.error_code))
        return "telegram_error"

    def _sanitize_error_code(self, error_code: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_]+", "_", error_code.strip().lower()).strip("_")
        return sanitized[:100] or "telegram_error"

    def _sanitize_error_message(self, error: TelegramDeliveryError) -> str:
        message = str(error) or "Telegram delivery failed"
        for secret in (
            settings.telegram_customer_bot_token,
            settings.telegram_bot_token,
            settings.telegram_webapp_bot_token,
            settings.telegram_customer_webhook_secret,
            settings.telegram_seller_webhook_secret,
        ):
            if secret:
                message = message.replace(secret, "[redacted]")
        message = " ".join(message.split())
        if error.retry_after_seconds is not None and "retry_after_seconds" not in message:
            message = f"{message} retry_after_seconds={error.retry_after_seconds}"
        return message[:TELEGRAM_ERROR_MESSAGE_MAX_LENGTH]

    def _order_created_message(self, payload: Mapping[str, object]) -> str:
        order_label = self._order_label(payload)
        total_amount = self._payload_value(payload, "total_amount", fallback="0.00")
        return (
            f"{ORDER_CREATED_CUSTOMER_MESSAGE}\n\n"
            f"Заказ {order_label} создан. Сумма: {total_amount}."
        )

    def _status_event_and_message(self, payload: Mapping[str, object]) -> tuple[str, str]:
        order_label = self._order_label(payload)
        new_status = self._payload_value(payload, "new_status", fallback="unknown")
        status_messages: dict[str, tuple[str, str]] = {
            OrderStatus.PROCESSING.value: (
                ORDER_PROCESSING_CUSTOMER,
                f"{ORDER_PROCESSING_CUSTOMER_MESSAGE}\n\nЗаказ {order_label} принят в обработку.",
            ),
            OrderStatus.SHIPPED.value: (
                ORDER_SHIPPED_CUSTOMER,
                f"{ORDER_SHIPPED_CUSTOMER_MESSAGE}\n\nЗаказ {order_label} отправлен.",
            ),
            OrderStatus.DELIVERED.value: (
                ORDER_DELIVERED_CUSTOMER,
                f"{ORDER_DELIVERED_CUSTOMER_MESSAGE}\n\nЗаказ {order_label} доставлен.",
            ),
            OrderStatus.CANCELLED.value: (
                ORDER_CANCELLED_CUSTOMER,
                f"{ORDER_CANCELLED_CUSTOMER_MESSAGE}\n\nЗаказ {order_label} отменён.",
            ),
        }
        mapped = status_messages.get(new_status)
        if mapped is not None:
            return mapped
        return (
            ORDER_STATUS_CHANGED_CUSTOMER,
            f"{ORDER_STATUS_CHANGED_CUSTOMER_MESSAGE}\n\n"
            f"Статус заказа {order_label}: {order_status_label(new_status)}.",
        )

    def _order_label(self, payload: Mapping[str, object]) -> str:
        order_id = self._payload_value(payload, "order_id", fallback="unknown")
        return self._payload_value(payload, "order_number", fallback=f"#{order_id}")

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

    def _payload_int(self, payload: Mapping[str, object], key: str) -> int | None:
        value = payload.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def _audit_delivery(
        self,
        delivery: CustomerServiceNotificationDelivery,
        *,
        action: str,
    ) -> None:
        await self.audit_service.record_action(
            actor_user_id=None,
            action=action,
            entity_type="customer_service_notification_delivery",
            entity_id=delivery.id,
            after_data={
                "id": delivery.id,
                "user_id": delivery.user_id,
                "order_id": delivery.order_id,
                "event_name": delivery.event_name,
                "status": delivery.status.value,
                "error_code": delivery.error_code,
            },
            metadata={"source": "customer_order_service_notification"},
            commit=False,
        )

    async def _flush_if_supported(self) -> None:
        flush = getattr(self.session, "flush", None)
        if callable(flush):
            await flush()

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc

    def _now(self) -> datetime:
        return self.now_factory()


class CustomerServiceNotificationEventPublisher:
    """Post-commit order event bridge for customer Bot 1 service notifications."""

    def __init__(
        self,
        session: AsyncSession,
        delivery_service: CustomerServiceNotificationDeliveryService | None = None,
    ) -> None:
        self.delivery_service = delivery_service or CustomerServiceNotificationDeliveryService(
            session
        )

    async def emit(self, name: str, payload: Mapping[str, object]) -> None:
        try:
            await self.delivery_service.handle_order_event(name=name, payload=payload)
        except Exception:
            logger.warning(
                "Failed to process customer service notification event %s",
                name,
                exc_info=True,
            )


class CustomerNotificationsService:
    """Customer Bot 1 subscription registry and consent business logic."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        telegram_service: TelegramService | None = None,
        audit_service: AuditService | None = None,
        now_factory: Any | None = None,
    ) -> None:
        self.session = session
        self.repository = CustomerNotificationsRepository(session)
        self.users_repository = UsersRepository(session)
        self.telegram_service = telegram_service or TelegramService(
            bot_token=settings.telegram_customer_bot_token,
        )
        self.audit_service = audit_service or AuditService(session)
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    async def get_my_subscription(self, user: User) -> CustomerSubscriptionMe:
        subscription = await self._get_or_link_subscription_for_user(user, commit_link=True)
        return self._me_response(subscription)

    async def update_my_subscription(
        self,
        *,
        user: User,
        payload: CustomerSubscriptionUpdate,
    ) -> CustomerSubscriptionMe:
        subscription = await self._get_or_create_subscription_for_user(user)
        before_data = self._subscription_snapshot(subscription)
        now = self._now()

        if payload.service_opt_in is not None:
            if payload.service_opt_in and self._has_service_send_target(subscription):
                subscription.service_opt_in = True
                subscription.service_opted_out_at = None
                subscription.opt_in_source = "mini_app_profile"
            elif not payload.service_opt_in:
                subscription.service_opt_in = False
                subscription.service_opted_out_at = now

        if payload.marketing_opt_in is not None:
            if payload.marketing_opt_in and self._has_active_private_chat(subscription):
                subscription.marketing_opt_in = True
                subscription.marketing_opted_in_at = now
                subscription.marketing_opted_out_at = None
                subscription.opt_in_source = "mini_app_profile"
            elif not payload.marketing_opt_in:
                subscription.marketing_opt_in = False
                subscription.marketing_opted_out_at = now

        await self._audit_if_changed(
            subscription=subscription,
            before_data=before_data,
            actor_user_id=user.id,
            source="mini_app_profile",
        )
        await self._commit("Customer notification subscription update failed")
        await self._refresh(subscription)
        return self._me_response(subscription)

    async def record_write_access_result(
        self,
        *,
        user: User,
        payload: CustomerWriteAccessRequest,
    ) -> CustomerSubscriptionMe:
        subscription = await self._get_or_create_subscription_for_user(user)
        before_data = self._subscription_snapshot(subscription)
        now = self._now()

        if payload.granted:
            subscription.write_access_granted = True
            subscription.write_access_granted_at = now
            subscription.write_access_denied_at = None
            subscription.write_access_source = payload.source
            subscription.service_opt_in = True
            subscription.service_opted_out_at = None
            subscription.opt_in_source = payload.source
        else:
            subscription.write_access_granted = False
            subscription.write_access_denied_at = now
            subscription.write_access_source = payload.source

        await self._audit_if_changed(
            subscription=subscription,
            before_data=before_data,
            actor_user_id=user.id,
            source=payload.source,
        )
        await self._commit("Customer notification write access update failed")
        await self._refresh(subscription)
        return self._me_response(subscription)

    async def create_start_link(self, _: User) -> CustomerSubscriptionStartLink:
        return self._start_link()

    async def list_subscriptions(
        self,
        *,
        limit: int,
        offset: int,
        has_chat: bool | None = None,
        service_opt_in: bool | None = None,
        marketing_opt_in: bool | None = None,
        blocked: bool | None = None,
        user_id: int | None = None,
        telegram_username: str | None = None,
    ) -> CustomerSubscriptionList:
        items, total = await self.repository.list(
            limit=limit,
            offset=offset,
            has_chat=has_chat,
            service_opt_in=service_opt_in,
            marketing_opt_in=marketing_opt_in,
            blocked=blocked,
            user_id=user_id,
            telegram_username=telegram_username,
        )
        return CustomerSubscriptionList(
            items=[self._admin_response(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def list_service_deliveries(
        self,
        *,
        limit: int,
        offset: int,
        status: CustomerServiceNotificationDeliveryStatus | None = None,
        event_name: str | None = None,
        user_id: int | None = None,
        order_id: int | None = None,
    ) -> CustomerServiceNotificationDeliveryList:
        items, total = await self.repository.list_service_deliveries(
            limit=limit,
            offset=offset,
            status=status,
            event_name=event_name,
            user_id=user_id,
            order_id=order_id,
        )
        return CustomerServiceNotificationDeliveryList(
            items=[CustomerServiceNotificationDeliveryRead.model_validate(item) for item in items],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def handle_start(
        self,
        message: TelegramMessage,
        *,
        start_payload: str,
    ) -> CustomerBotWebhookResponse:
        if not self._is_private_message(message):
            await self._send_chat_message(message.chat.id, CONNECT_PRIVATE_CHAT_MESSAGE)
            return self._response(handled=True, result="private_chat_required")
        if message.from_user is None:
            return self._response(handled=False, result="missing_telegram_user")

        subscription = await self._upsert_from_private_message(message)
        before_data = self._subscription_snapshot(subscription)
        now = self._now()

        subscription.has_chat = True
        subscription.service_opt_in = True
        subscription.service_opted_out_at = None
        subscription.marketing_opt_in = True
        subscription.marketing_opted_in_at = now
        subscription.marketing_opted_out_at = None
        subscription.blocked_at = None
        subscription.last_delivery_error = None
        subscription.last_start_at = now
        subscription.opt_in_source = "bot_start"

        await self._audit_if_changed(
            subscription=subscription,
            before_data=before_data,
            actor_user_id=subscription.user_id,
            source="bot_start",
        )
        await self._commit("Customer notification subscription start failed")
        await self._send_chat_message(message.chat.id, WELCOME_MESSAGE)
        result = "started_with_payload" if start_payload else "started"
        return self._response(handled=True, result=result)

    async def handle_stop(self, message: TelegramMessage) -> CustomerBotWebhookResponse:
        if not self._is_private_message(message):
            return self._response(handled=False, result="ignored_non_private_stop")
        if message.from_user is None:
            return self._response(handled=False, result="missing_telegram_user")

        subscription = await self._upsert_from_private_message(message)
        before_data = self._subscription_snapshot(subscription)
        now = self._now()
        subscription.service_opt_in = False
        subscription.marketing_opt_in = False
        subscription.service_opted_out_at = now
        subscription.marketing_opted_out_at = now
        subscription.last_stop_at = now

        await self._audit_if_changed(
            subscription=subscription,
            before_data=before_data,
            actor_user_id=subscription.user_id,
            source="bot_stop",
        )
        await self._commit("Customer notification subscription stop failed")
        await self._send_chat_message(message.chat.id, STOP_MESSAGE)
        return self._response(handled=True, result="stopped")

    async def handle_settings(self, message: TelegramMessage) -> CustomerBotWebhookResponse:
        if not self._is_private_message(message):
            return self._response(handled=False, result="ignored_non_private_settings")
        if message.from_user is None:
            return self._response(handled=False, result="missing_telegram_user")

        subscription = await self._upsert_from_private_message(message)
        subscription.last_settings_at = self._now()
        await self._commit("Customer notification settings update failed")
        await self._send_settings_message(message.chat.id, subscription=subscription)
        return self._response(handled=True, result="settings_sent")

    async def handle_callback_query(
        self,
        callback_query: TelegramCallbackQuery,
    ) -> CustomerBotWebhookResponse:
        parsed = self._parse_callback_data(callback_query.data)
        if parsed is None:
            await self._answer_callback(callback_query.id, "Настройка недоступна.")
            return self._response(handled=False, result="unsupported_callback")
        if callback_query.message is None:
            await self._answer_callback(callback_query.id, "Откройте настройки заново.")
            return self._response(handled=False, result="callback_without_message")
        if not self._is_private_message(callback_query.message):
            await self._answer_callback(callback_query.id, "Настройки доступны в личном чате.")
            return self._response(handled=True, result="private_chat_required")

        message = callback_query.message
        subscription = await self._upsert_from_callback(callback_query, message)
        before_data = self._subscription_snapshot(subscription)
        consent_type, enabled = parsed
        now = self._now()

        if consent_type == "service":
            subscription.service_opt_in = enabled
            subscription.service_opted_out_at = None if enabled else now
        else:
            subscription.marketing_opt_in = enabled
            if enabled:
                subscription.marketing_opted_in_at = now
                subscription.marketing_opted_out_at = None
                subscription.opt_in_source = "bot_settings"
            else:
                subscription.marketing_opted_out_at = now

        subscription.last_settings_at = now
        await self._audit_if_changed(
            subscription=subscription,
            before_data=before_data,
            actor_user_id=subscription.user_id,
            source="bot_settings",
        )
        await self._commit("Customer notification settings callback failed")
        await self._answer_callback(callback_query.id, "Настройки обновлены.")
        await self._send_settings_message(message.chat.id, subscription=subscription)
        callback_result = f"{consent_type}_{'enabled' if enabled else 'disabled'}"
        return self._response(handled=True, result=callback_result)

    async def _get_or_link_subscription_for_user(
        self,
        user: User,
        *,
        commit_link: bool,
    ) -> CustomerTelegramSubscription | None:
        subscription = await self.repository.get_by_user_id(user.id)
        if subscription is not None:
            return subscription

        subscription = await self.repository.link_unlinked_subscription_to_user(
            user_id=user.id,
            telegram_user_id=user.telegram_id,
        )
        if subscription is None:
            return None
        if subscription.user_id == user.id and commit_link:
            try:
                await self._commit("Customer notification subscription link failed")
                await self._refresh(subscription)
            except AppError:
                logger.warning(
                    "customer notification subscription auto-link conflict",
                    extra={"user_id": user.id, "telegram_user_id": user.telegram_id},
                )
                return await self.repository.get_by_user_id(user.id)
        return subscription

    async def _get_or_create_subscription_for_user(
        self,
        user: User,
    ) -> CustomerTelegramSubscription:
        subscription = await self._get_or_link_subscription_for_user(user, commit_link=False)
        if subscription is not None:
            return subscription

        subscription = CustomerTelegramSubscription(
            user_id=user.id,
            telegram_user_id=user.telegram_id,
            chat_type=UNKNOWN_CHAT_TYPE,
            has_chat=False,
            service_opt_in=False,
            marketing_opt_in=False,
            write_access_granted=False,
        )
        self.repository.add(subscription)
        return subscription

    async def _upsert_from_private_message(
        self,
        message: TelegramMessage,
    ) -> CustomerTelegramSubscription:
        if message.from_user is None:
            raise AppError("Telegram user is missing", status.HTTP_400_BAD_REQUEST)
        subscription = await self._upsert_by_telegram_user_id(message.from_user.id)
        self._update_telegram_fields(subscription, message)
        return subscription

    async def _upsert_from_callback(
        self,
        callback_query: TelegramCallbackQuery,
        message: TelegramMessage,
    ) -> CustomerTelegramSubscription:
        subscription = await self._upsert_by_telegram_user_id(callback_query.from_user.id)
        self._update_telegram_fields(
            subscription,
            message,
            callback_user=callback_query.from_user,
        )
        return subscription

    async def _upsert_by_telegram_user_id(
        self,
        telegram_user_id: int,
    ) -> CustomerTelegramSubscription:
        user = await self.users_repository.get_by_telegram_id(telegram_user_id)
        subscription = await self.repository.get_by_telegram_user_id(telegram_user_id)
        if subscription is None and user is not None:
            subscription = await self.repository.get_by_user_id(user.id)
        if subscription is None:
            subscription = CustomerTelegramSubscription(
                user_id=user.id if user is not None else None,
                telegram_user_id=telegram_user_id,
                chat_type=UNKNOWN_CHAT_TYPE,
                has_chat=False,
                service_opt_in=False,
                marketing_opt_in=False,
                write_access_granted=False,
            )
            self.repository.add(subscription)
        elif user is not None and subscription.user_id is None:
            subscription.user_id = user.id
        return subscription

    def _update_telegram_fields(
        self,
        subscription: CustomerTelegramSubscription,
        message: TelegramMessage,
        *,
        callback_user: Any | None = None,
    ) -> None:
        telegram_user = callback_user or message.from_user
        if telegram_user is not None:
            subscription.telegram_username = telegram_user.username
            subscription.telegram_first_name = telegram_user.first_name
            subscription.telegram_last_name = telegram_user.last_name

        subscription.telegram_chat_id = message.chat.id
        subscription.chat_type = message.chat.type or UNKNOWN_CHAT_TYPE
        subscription.has_chat = (
            subscription.chat_type == PRIVATE_CHAT_TYPE and subscription.blocked_at is None
        )

    async def _audit_if_changed(
        self,
        *,
        subscription: CustomerTelegramSubscription,
        before_data: dict[str, Any],
        actor_user_id: int | None,
        source: str,
    ) -> None:
        after_data = self._subscription_snapshot(subscription)
        if before_data == after_data:
            return
        await self._flush_if_supported()
        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action=ACTION_SUBSCRIPTION_UPDATED,
            entity_type="customer_telegram_subscription",
            entity_id=subscription.id,
            before_data=before_data,
            after_data=after_data,
            metadata={"source": source},
            commit=False,
        )

    async def _send_settings_message(
        self,
        chat_id: int,
        *,
        subscription: CustomerTelegramSubscription | None,
        intro: str | None = None,
    ) -> None:
        lines = []
        if intro:
            lines.append(intro)
            lines.append("")
        if subscription is None:
            lines.append("Настройки уведомлений пока не найдены. Отправьте /start.")
            reply_markup = None
        else:
            lines.append(self._settings_text(subscription))
            reply_markup = self._settings_reply_markup(subscription)
        await self._send_chat_message(chat_id, "\n".join(lines), reply_markup=reply_markup)

    def _settings_text(self, subscription: CustomerTelegramSubscription) -> str:
        chat_state = "подключен" if self._has_active_private_chat(subscription) else "не подключен"
        service_state = "включены" if subscription.service_opt_in else "выключены"
        marketing_state = "включены" if subscription.marketing_opt_in else "выключены"
        return "\n".join(
            (
                "Настройки уведомлений",
                f"Чат: {chat_state}",
                f"Заказы: {service_state}",
                f"Акции: {marketing_state}",
                "/stop отключит сообщения.",
            )
        )

    def _settings_reply_markup(
        self,
        subscription: CustomerTelegramSubscription,
    ) -> dict[str, object]:
        service_action = "off" if subscription.service_opt_in else "on"
        marketing_action = "off" if subscription.marketing_opt_in else "on"
        return {
            "inline_keyboard": [
                [
                    {
                        "text": (
                            "Выключить заказы" if subscription.service_opt_in else "Включить заказы"
                        ),
                        "callback_data": f"{CALLBACK_PREFIX}:service:{service_action}",
                    }
                ],
                [
                    {
                        "text": (
                            "Выключить предложения"
                            if subscription.marketing_opt_in
                            else "Включить предложения"
                        ),
                        "callback_data": f"{CALLBACK_PREFIX}:marketing:{marketing_action}",
                    }
                ],
            ]
        }

    async def _send_chat_message(
        self,
        chat_id: int,
        message: str,
        *,
        reply_markup: dict[str, object] | None = None,
    ) -> bool:
        try:
            await self.telegram_service.send_message(
                str(chat_id),
                message,
                reply_markup=reply_markup,
            )
        except TelegramDeliveryError:
            return False
        return True

    async def _answer_callback(self, callback_query_id: str, text: str) -> bool:
        try:
            await self.telegram_service.answer_callback_query(callback_query_id, text=text)
        except TelegramDeliveryError:
            return False
        return True

    def _parse_callback_data(self, data: str | None) -> tuple[str, bool] | None:
        if not data:
            return None
        parts = data.split(":")
        if len(parts) != 3 or parts[0] != CALLBACK_PREFIX:
            return None
        consent_type, action = parts[1], parts[2]
        if consent_type not in {"service", "marketing"} or action not in {"on", "off"}:
            return None
        return consent_type, action == "on"

    def _is_private_message(self, message: TelegramMessage) -> bool:
        return message.chat.type == PRIVATE_CHAT_TYPE

    def _has_active_private_chat(self, subscription: CustomerTelegramSubscription) -> bool:
        return has_active_private_chat(subscription)

    def _has_service_send_target(self, subscription: CustomerTelegramSubscription) -> bool:
        return resolve_customer_service_send_target(subscription) is not None

    def _me_response(
        self,
        subscription: CustomerTelegramSubscription | None,
    ) -> CustomerSubscriptionMe:
        start_link = self._start_link()
        if subscription is None:
            return CustomerSubscriptionMe(
                has_chat=False,
                write_access_granted=False,
                service_notifications_available=False,
                availability_status="permission_required",
                availability_reason="no_subscription",
                service_opt_in=False,
                marketing_opt_in=False,
                blocked_at=None,
                write_access_granted_at=None,
                write_access_denied_at=None,
                telegram_username=None,
                bot_start_link=start_link.bot_start_link,
                start_command=start_link.start_command,
            )

        has_chat = self._has_active_private_chat(subscription)
        availability_status, availability_reason = self._subscription_availability(subscription)
        service_notifications_available = availability_status == "available"
        return CustomerSubscriptionMe(
            has_chat=has_chat,
            write_access_granted=bool(subscription.write_access_granted),
            service_notifications_available=service_notifications_available,
            availability_status=availability_status,
            availability_reason=availability_reason,
            service_opt_in=subscription.service_opt_in,
            marketing_opt_in=subscription.marketing_opt_in,
            blocked_at=subscription.blocked_at,
            write_access_granted_at=subscription.write_access_granted_at,
            write_access_denied_at=subscription.write_access_denied_at,
            telegram_username=subscription.telegram_username,
            bot_start_link=None if service_notifications_available else start_link.bot_start_link,
            start_command=start_link.start_command,
        )

    def _admin_response(
        self,
        subscription: CustomerTelegramSubscription,
    ) -> CustomerSubscriptionAdminRead:
        return CustomerSubscriptionAdminRead(
            id=subscription.id,
            user_id=subscription.user_id,
            telegram_user_id=subscription.telegram_user_id,
            telegram_chat_id_masked=self._mask_chat_id(subscription.telegram_chat_id),
            telegram_username=subscription.telegram_username,
            telegram_first_name=subscription.telegram_first_name,
            telegram_last_name=subscription.telegram_last_name,
            chat_type=subscription.chat_type,
            has_chat=subscription.has_chat,
            write_access_granted=bool(subscription.write_access_granted),
            service_opt_in=subscription.service_opt_in,
            marketing_opt_in=subscription.marketing_opt_in,
            blocked_at=subscription.blocked_at,
            write_access_granted_at=subscription.write_access_granted_at,
            write_access_denied_at=subscription.write_access_denied_at,
            last_start_at=subscription.last_start_at,
            last_stop_at=subscription.last_stop_at,
            last_settings_at=subscription.last_settings_at,
            last_delivery_error=subscription.last_delivery_error,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )

    def _subscription_availability(
        self,
        subscription: CustomerTelegramSubscription,
    ) -> tuple[str, str | None]:
        if subscription.blocked_at is not None:
            return "bot_blocked", "blocked"
        has_send_target = self._has_service_send_target(subscription)
        if has_send_target and subscription.service_opt_in:
            return "available", None
        if has_send_target and not subscription.service_opt_in:
            return "service_opt_out", "service_opt_in_false"
        if subscription.write_access_denied_at is not None:
            return "permission_denied", "write_access_denied"
        return "permission_required", "no_private_chat_or_write_access"

    def _start_link(self) -> CustomerSubscriptionStartLink:
        username = (settings.telegram_customer_bot_username or "").strip().lstrip("@")
        start_command = f"/start {START_LINK_PAYLOAD}"
        bot_start_link = None
        if username:
            bot_start_link = f"https://t.me/{quote(username)}?start={quote(START_LINK_PAYLOAD)}"
        return CustomerSubscriptionStartLink(
            bot_start_link=bot_start_link,
            start_command=start_command,
        )

    def _subscription_snapshot(
        self,
        subscription: CustomerTelegramSubscription,
    ) -> dict[str, Any]:
        return {
            "user_id": subscription.user_id,
            "telegram_user_id": subscription.telegram_user_id,
            "has_chat": subscription.has_chat,
            "chat_type": subscription.chat_type,
            "write_access_granted": bool(subscription.write_access_granted),
            "write_access_granted_at": (
                subscription.write_access_granted_at.isoformat()
                if subscription.write_access_granted_at is not None
                else None
            ),
            "write_access_denied_at": (
                subscription.write_access_denied_at.isoformat()
                if subscription.write_access_denied_at is not None
                else None
            ),
            "service_opt_in": subscription.service_opt_in,
            "marketing_opt_in": subscription.marketing_opt_in,
            "blocked_at": (
                subscription.blocked_at.isoformat() if subscription.blocked_at is not None else None
            ),
        }

    def _mask_chat_id(self, chat_id: int | None) -> str | None:
        if chat_id is None:
            return None
        value = str(chat_id)
        prefix = "-" if value.startswith("-") else ""
        tail = value[-4:] if len(value) > 4 else value
        return f"{prefix}***{tail}"

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc

    async def _flush_if_supported(self) -> None:
        flush = getattr(self.session, "flush", None)
        if callable(flush):
            await flush()

    async def _refresh(self, subscription: CustomerTelegramSubscription) -> None:
        refresh = getattr(self.session, "refresh", None)
        if callable(refresh):
            await refresh(subscription)

    def _now(self) -> datetime:
        return self.now_factory()

    def _response(self, *, handled: bool, result: str) -> CustomerBotWebhookResponse:
        return CustomerBotWebhookResponse(handled=handled, result=result)


class CustomerBotWebhookService:
    """Telegram webhook adapter for Bot 1 customer updates."""

    def __init__(self, customer_notifications_service: CustomerNotificationsService) -> None:
        self.customer_notifications_service = customer_notifications_service

    async def handle_update(self, update: TelegramUpdate) -> CustomerBotWebhookResponse:
        if update.callback_query is not None:
            return await self.customer_notifications_service.handle_callback_query(
                update.callback_query
            )

        message = update.message
        if message is None or message.text is None:
            return CustomerBotWebhookResponse(handled=False, result="unsupported_update")

        text = message.text.strip()
        start_match = START_COMMAND_RE.match(text)
        if start_match is not None:
            return await self.customer_notifications_service.handle_start(
                message,
                start_payload=(start_match.group("payload") or "").strip(),
            )

        command_match = COMMAND_RE.match(text)
        if command_match is None:
            return CustomerBotWebhookResponse(handled=False, result="ignored")

        command = command_match.group("command").lower()
        if command == "/stop":
            return await self.customer_notifications_service.handle_stop(message)
        if command == "/settings":
            return await self.customer_notifications_service.handle_settings(message)

        return CustomerBotWebhookResponse(handled=False, result="ignored")
