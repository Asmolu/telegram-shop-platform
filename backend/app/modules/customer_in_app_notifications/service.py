from datetime import UTC, datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    CustomerInAppNotification,
    ManualPayment,
    ManualPaymentStatus,
    Order,
    OrderStatus,
    ReturnRequest,
    ReturnRequestStatus,
    SellerPaymentSettings,
)
from app.db.models import (
    CustomerInAppNotificationActionMode as ActionMode,
)
from app.db.models import (
    CustomerInAppNotificationCategory as Category,
)
from app.db.models import (
    CustomerInAppNotificationVariant as Variant,
)
from app.modules.customer_in_app_notifications.repository import (
    CustomerInAppNotificationsRepository,
)
from app.modules.customer_in_app_notifications.schemas import (
    CustomerInAppNotificationRead,
    CustomerInAppNotificationSeenRead,
)

ORDER_COPY = {
    OrderStatus.NEW: (
        "Статус заказа обновлён",
        "Заказ {number} получил статус «Новый».",
        ActionMode.CONTINUE_ONLY,
    ),
    OrderStatus.PROCESSING: (
        "Заказ принят в обработку",
        "Заказ {number} принят продавцом и готовится к отправке.",
        ActionMode.CONTINUE_ONLY,
    ),
    OrderStatus.SHIPPED: (
        "Заказ отправлен",
        "Заказ {number} передан в доставку.",
        ActionMode.CONTINUE_ONLY,
    ),
    OrderStatus.DELIVERED: (
        "Заказ доставлен",
        "Заказ {number} получил статус «Доставлено».",
        ActionMode.CONTINUE_ONLY,
    ),
    OrderStatus.CANCELLED: (
        "Заказ отменён",
        "Заказ {number} был отменён.",
        ActionMode.CONTINUE_WITH_CONTACTS,
    ),
}
PAYMENT_COPY = {
    ManualPaymentStatus.SUBMITTED: (
        "Оплата отправлена на проверку",
        "Оплата заказа {number} передана продавцу на проверку.",
        ActionMode.CONTINUE_ONLY,
    ),
    ManualPaymentStatus.APPROVED: (
        "Оплата подтверждена",
        "Оплата заказа {number} подтверждена.",
        ActionMode.CONTINUE_WITH_CONTACTS,
    ),
    ManualPaymentStatus.REJECTED: (
        "Оплата отклонена",
        "Оплата заказа {number} не была подтверждена.",
        ActionMode.CONTINUE_WITH_CONTACTS,
    ),
    ManualPaymentStatus.EXPIRED: (
        "Время оплаты истекло",
        "Время, отведённое на оплату заказа {number}, истекло.",
        ActionMode.CONTINUE_WITH_CONTACTS,
    ),
    ManualPaymentStatus.CANCELLED: (
        "Оплата отменена",
        "Оплата заказа {number} была отменена.",
        ActionMode.CONTINUE_WITH_CONTACTS,
    ),
}
RETURN_COPY = {
    ReturnRequestStatus.APPROVED: ("Возврат одобрен", "Заявка на возврат {number} была одобрена."),
    ReturnRequestStatus.REJECTED: (
        "В возврате отказано",
        "Заявка на возврат {number} была отклонена.",
    ),
    ReturnRequestStatus.COMPLETED: ("Возврат завершён", "Работа по заявке {number} завершена."),
    ReturnRequestStatus.CANCELLED: ("Возврат отменён", "Заявка на возврат {number} была отменена."),
}


class CustomerInAppNotificationsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CustomerInAppNotificationsRepository(session)

    async def create_order_status(
        self,
        order: Order,
        *,
        source_key: str,
        occurred_at: datetime | None = None,
    ) -> None:
        copy = ORDER_COPY.get(order.status)
        if copy is None:
            return
        title, message, action_mode = copy
        await self.repository.insert_if_source_absent(
            CustomerInAppNotification(
                user_id=order.user_id,
                category=Category.ORDER,
                event_code=order.status.value,
                variant=Variant.STANDARD,
                action_mode=action_mode,
                order_id=order.id,
                title=title,
                message=message.format(number=order.order_number),
                payload={"order_number": order.order_number, "order_status": order.status.value},
                occurred_at=occurred_at or datetime.now(UTC),
                source_key=source_key,
            )
        )

    async def create_payment_status(
        self, payment: ManualPayment, *, occurred_at: datetime | None = None, legacy: bool = False
    ) -> None:
        copy = PAYMENT_COPY.get(payment.status)
        if copy is None:
            return
        title, message, action_mode = copy
        variant = (
            Variant.APPROVED_PAYMENT
            if payment.status == ManualPaymentStatus.APPROVED
            else Variant.STANDARD
        )
        payload: dict[str, object] = {
            "order_number": payment.order.order_number,
            "payment_status": payment.status.value,
            "order_status": payment.order.status.value,
            "total_amount": str(payment.order.total_amount),
            "delivery_method": payment.order.delivery_method.value
            if payment.order.delivery_method
            else None,
            "order_created_at": (
                payment.order.created_at or occurred_at or datetime.now(UTC)
            ).isoformat(),
            "legacy": legacy,
        }
        if variant == Variant.APPROVED_PAYMENT:
            result = await self.session.execute(
                select(SellerPaymentSettings).where(SellerPaymentSettings.id == 1)
            )
            banner = result.scalar_one_or_none()
            image_path = (
                banner.payment_success_banner_image_path
                if banner and banner.payment_success_banner_enabled
                else None
            )
            payload.update(
                {
                    "image_path": image_path,
                    "image_url": settings.public_upload_url_for(image_path) if image_path else None,
                }
            )
        await self.repository.insert_if_source_absent(
            CustomerInAppNotification(
                user_id=payment.order.user_id,
                category=Category.PAYMENT,
                event_code=payment.status.value,
                variant=variant,
                action_mode=action_mode,
                order_id=payment.order_id,
                manual_payment_id=payment.id,
                title=title,
                message=message.format(number=payment.order.order_number),
                payload=payload,
                occurred_at=occurred_at or datetime.now(UTC),
                source_key=f"payment:{payment.id}:{payment.status.value}",
            )
        )

    async def create_return_status(
        self, return_request: ReturnRequest, *, occurred_at: datetime | None = None
    ) -> None:
        copy = RETURN_COPY.get(return_request.status)
        if copy is None:
            return
        title, message = copy
        await self.repository.insert_if_source_absent(
            CustomerInAppNotification(
                user_id=return_request.user_id,
                category=Category.RETURN,
                event_code=return_request.status.value,
                variant=Variant.STANDARD,
                action_mode=ActionMode.CONTINUE_WITH_CONTACTS,
                order_id=return_request.order_id,
                return_request_id=return_request.id,
                title=title,
                message=message.format(number=return_request.return_number),
                payload={
                    "return_number": return_request.return_number,
                    "return_status": return_request.status.value,
                },
                occurred_at=occurred_at or datetime.now(UTC),
                source_key=f"return:{return_request.id}:{return_request.status.value}",
            )
        )

    async def pending(self, *, user_id: int, limit: int) -> list[CustomerInAppNotificationRead]:
        items = await self.repository.list_pending(user_id=user_id, limit=limit)
        if not items:
            legacy_order = await self.repository.get_legacy_approved_order(user_id=user_id)
            if legacy_order and legacy_order.manual_payment:
                await self.create_payment_status(legacy_order.manual_payment, legacy=True)
                await self.session.commit()
            items = await self.repository.list_pending(user_id=user_id, limit=limit)
        return [CustomerInAppNotificationRead.model_validate(item) for item in items]

    async def mark_seen(
        self, *, notification_id: int, user_id: int
    ) -> CustomerInAppNotificationSeenRead:
        item = await self.repository.get_for_user(
            notification_id=notification_id, user_id=user_id, for_update=True
        )
        if item is None:
            raise AppError("Notification not found", status.HTTP_404_NOT_FOUND)
        if item.seen_at is None:
            item.seen_at = datetime.now(UTC)
            if item.variant == Variant.APPROVED_PAYMENT and item.order_id is not None:
                order = await self.session.get(Order, item.order_id)
                if (
                    order is not None
                    and order.user_id == user_id
                    and order.payment_success_banner_seen_at is None
                ):
                    order.payment_success_banner_seen_at = item.seen_at
            await self.session.commit()
        return CustomerInAppNotificationSeenRead(id=item.id, seen_at=item.seen_at)

    async def mark_legacy_source_seen(self, *, payment_id: int, seen_at: datetime) -> None:
        item = await self.repository.get_by_source_key(f"payment:{payment_id}:APPROVED")
        if item is not None and item.seen_at is None:
            item.seen_at = seen_at


class NoopCustomerInAppNotificationsService:
    """Test-double boundary for legacy unit sessions without ORM persistence methods."""

    async def create_order_status(self, *args, **kwargs) -> None:
        return None

    async def create_payment_status(self, *args, **kwargs) -> None:
        return None

    async def create_return_status(self, *args, **kwargs) -> None:
        return None

    async def mark_legacy_source_seen(self, *args, **kwargs) -> None:
        return None


def notification_service_for_session(session):
    if hasattr(session, "add") and hasattr(session, "execute"):
        return CustomerInAppNotificationsService(session)
    return NoopCustomerInAppNotificationsService()
