import hashlib
import logging
import mimetypes
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import join_public_url, settings
from app.core.errors import AppError
from app.db.models import (
    ManualPayment,
    ManualPaymentCurrency,
    ManualPaymentMethod,
    ManualPaymentStatus,
    Order,
    OrderStatus,
    SellerPaymentSettings,
    UserRole,
)
from app.events.names import (
    MANUAL_PAYMENT_APPROVED,
    MANUAL_PAYMENT_EXPIRED,
    MANUAL_PAYMENT_REJECTED,
    MANUAL_PAYMENT_SUBMITTED,
)
from app.modules.audit.service import AuditService, NoopAuditService
from app.modules.customer_in_app_notifications.service import notification_service_for_session
from app.modules.customer_notifications.service import CustomerServiceNotificationEventPublisher
from app.modules.idempotency.service import IdempotencyClaim, IdempotencyService
from app.modules.manual_payments.phone import normalize_russian_phone
from app.modules.manual_payments.repository import ManualPaymentsRepository
from app.modules.manual_payments.schemas import (
    ManualPaymentList,
    ManualPaymentRead,
    SellerPaymentSettingsRead,
    SellerPaymentSettingsUpdate,
)
from app.modules.orders.delivery import delivery_method_label
from app.modules.outbox.constants import CUSTOMER_CONSUMER, SELLER_CONSUMER
from app.modules.outbox.service import OutboxService
from app.modules.telegram.service import TelegramDeliveryError, TelegramService
from app.modules.uploads.service import UploadsService
from app.modules.uploads.storage import LocalStorageService

logger = logging.getLogger(__name__)

PAYMENT_RESERVATION_MINUTES = 30
ACTIVE_PAYMENT_STATUSES = {
    ManualPaymentStatus.PENDING,
    ManualPaymentStatus.SUBMITTED,
}
SELLER_TIMEZONE = ZoneInfo("Europe/Moscow")


class PaymentEventPublisher(Protocol):
    async def emit(self, name: str, payload: Mapping[str, object]) -> None:
        """Deliver a post-commit payment event."""


class ManualPaymentEventPublisher:
    def __init__(
        self,
        session: AsyncSession,
        *,
        telegram_service: TelegramService | None = None,
        customer_publisher: PaymentEventPublisher | None = None,
        storage: LocalStorageService | None = None,
    ) -> None:
        self.session = session
        self.repository = ManualPaymentsRepository(session)
        self.telegram_service = telegram_service or TelegramService()
        self.customer_publisher = customer_publisher or CustomerServiceNotificationEventPublisher(
            session
        )
        self.storage = storage or LocalStorageService()

    async def emit(self, name: str, payload: Mapping[str, object]) -> None:
        if name == MANUAL_PAYMENT_SUBMITTED:
            await self.emit_seller(name, payload)
            return
        if name in {
            MANUAL_PAYMENT_APPROVED,
            MANUAL_PAYMENT_REJECTED,
            MANUAL_PAYMENT_EXPIRED,
        }:
            try:
                await self.emit_seller(name, payload)
            except Exception:
                logger.warning(
                    "manual_payment.seller_bot_finalization_failed",
                    exc_info=True,
                    extra={
                        "payment_id": payload.get("payment_id"),
                        "order_id": payload.get("order_id"),
                    },
                )
            await self.customer_publisher.emit(name, payload)

    async def emit_seller(self, name: str, payload: Mapping[str, object]) -> None:
        if name == MANUAL_PAYMENT_SUBMITTED:
            await self._notify_seller(payload)
            return
        if name in {
            MANUAL_PAYMENT_APPROVED,
            MANUAL_PAYMENT_REJECTED,
            MANUAL_PAYMENT_EXPIRED,
        }:
            await self._finalize_seller_message(name, payload)

    async def _notify_seller(self, payload: Mapping[str, object]) -> None:
        payment_id = int(payload["payment_id"])
        order_id = int(payload["order_id"])
        notification_payload = dict(payload)
        payment = await self.repository.get_by_id(payment_id, populate_existing=True)
        if payment is not None:
            if payment.seller_telegram_message_id is not None:
                return
            notification_payload["receipt_image_path"] = payment.receipt_image_path
            notification_payload["has_receipt"] = bool(payment.receipt_image_path)
        message = self._review_message(notification_payload)
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Подтвердить",
                        "callback_data": f"manual_payment:approve:{payment_id}",
                    },
                    {
                        "text": "❌ Отклонить",
                        "callback_data": f"manual_payment:reject:{payment_id}",
                    },
                ]
            ]
        }
        bot_token = getattr(self.telegram_service, "bot_token", settings.telegram_bot_token)
        seller_chat_id = (
            getattr(self.telegram_service, "seller_chat_id", None)
            or settings.telegram_orders_notification_chat_id
        )
        receipt_path = self._receipt_path(notification_payload)
        logger.info(
            "manual_payment.seller_bot_notification_attempt",
            extra={
                "payment_id": payment_id,
                "order_id": order_id,
                "has_receipt": receipt_path is not None,
            },
        )
        if not bot_token or not seller_chat_id:
            raise TelegramDeliveryError(
                "Telegram seller notification is not configured",
                error_code="configuration_error",
            )
        if getattr(self.session, "in_transaction", lambda: False)():
            await self.session.commit()
        delivery_type = "text"
        if receipt_path is not None:
            try:
                photo = self.storage.read_bytes(receipt_path)
            except OSError as exc:
                logger.warning(
                    "manual_payment.seller_bot_receipt_read_failed",
                    extra={
                        "payment_id": payment_id,
                        "order_id": order_id,
                        "has_receipt_path": True,
                        "error_type": type(exc).__name__,
                    },
                )
                message = self._review_message(
                    {
                        **notification_payload,
                        "has_receipt": False,
                        "receipt_image_path": None,
                        "receipt_unavailable": True,
                    }
                )
                message_id = await self.telegram_service.send_message(
                    seller_chat_id,
                    message,
                    reply_markup=reply_markup,
                )
            else:
                filename = Path(receipt_path).name or f"payment-{payment_id}.jpg"
                mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
                message_id = await self.telegram_service.send_photo_bytes(
                    seller_chat_id,
                    photo,
                    filename=filename,
                    mime_type=mime_type,
                    caption=message,
                    reply_markup=reply_markup,
                )
                delivery_type = "photo"
                logger.info(
                    "manual_payment.seller_bot_receipt_photo_sent",
                    extra={
                        "payment_id": payment_id,
                        "order_id": order_id,
                        "has_receipt_path": True,
                    },
                )
        else:
            logger.info(
                "manual_payment.seller_bot_receipt_missing",
                extra={
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "has_receipt_path": False,
                },
            )
            message_id = await self.telegram_service.send_message(
                seller_chat_id,
                message,
                reply_markup=reply_markup,
            )
        if message_id is not None:
            if payment is not None:
                payment.seller_telegram_chat_id = int(seller_chat_id)
                payment.seller_telegram_message_id = message_id
                await self.session.commit()
        logger.info(
            "manual_payment.seller_bot_notification_sent",
            extra={
                "payment_id": payment_id,
                "order_id": order_id,
                "status": str(payload.get("status", ManualPaymentStatus.SUBMITTED.value)),
                "has_receipt": receipt_path is not None,
                "delivery_type": delivery_type,
            },
        )

    def _review_message(self, payload: Mapping[str, object]) -> str:
        payment_id = int(payload["payment_id"])
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
        amount = Decimal(str(payload["amount"]))
        amount_label = f"{amount:,.2f}".replace(",", " ").replace(".00", "")
        username = payload.get("customer_username")
        username_label = f"@{username}" if username else "—"
        has_receipt = bool(self._receipt_path(payload) or payload.get("has_receipt"))
        if payload.get("receipt_unavailable"):
            receipt_line = "Фото не удалось открыть\n"
        else:
            receipt_line = "" if has_receipt else "Без фото\n"
        return (
            "Проверка оплаты\n\n"
            f"Заказ {payload['order_number']}\n"
            f"Сумма: {amount_label} ₽\n"
            f"Клиент: {username_label} / ID {payload['user_id']}\n"
            f"Телефон клиента: {payload.get('customer_phone') or '—'}\n"
            f"Способ доставки: {payload.get('delivery_method_label') or '—'}\n"
            f"Комментарий к переводу: {payload['payment_comment']}\n"
            f"{receipt_line}"
            f"Резерв до: {expires_at.astimezone(SELLER_TIMEZONE).strftime('%H:%M')}\n"
            f"{_seller_panel_payment_url(payment_id)}"
        )

    async def _finalize_seller_message(
        self,
        name: str,
        payload: Mapping[str, object],
    ) -> None:
        chat_id = (
            payload.get("seller_telegram_chat_id")
            or settings.telegram_orders_notification_chat_id
        )
        message_id = payload.get("seller_telegram_message_id")
        final_line = self._final_payment_line(name, payload)
        final_message = f"{self._review_message(payload)}\n\n{final_line}"

        if not chat_id:
            raise TelegramDeliveryError(
                "Telegram seller notification is not configured",
                error_code="configuration_error",
            )

        if chat_id and message_id:
            edit_result = await self._edit_seller_message(
                chat_id=str(chat_id),
                message_id=int(message_id),
                message=final_message,
                prefer_caption=bool(self._receipt_path(payload) or payload.get("has_receipt")),
                payment_id=payload.get("payment_id"),
                order_id=payload.get("order_id"),
            )
            if edit_result is not None:
                logger.info(
                    "manual_payment.seller_bot_finalization_result",
                    extra={
                        "payment_id": payload.get("payment_id"),
                        "order_id": payload.get("order_id"),
                        "status": payload.get("status"),
                        "result": edit_result,
                    },
                )
                return
            await self._remove_seller_message_actions(
                chat_id=str(chat_id),
                message_id=int(message_id),
                payment_id=payload.get("payment_id"),
                order_id=payload.get("order_id"),
            )

        if chat_id:
            await self.telegram_service.send_message(
                str(chat_id),
                (
                    f"{final_line}\n"
                    f"Заказ: {payload['order_number']}\n"
                    f"Оплата: #{payload['payment_id']}"
                ),
            )
            logger.info(
                "manual_payment.seller_bot_finalization_result",
                extra={
                    "payment_id": payload.get("payment_id"),
                    "order_id": payload.get("order_id"),
                    "status": payload.get("status"),
                    "result": "follow_up",
                },
            )

    async def _edit_seller_message(
        self,
        *,
        chat_id: str,
        message_id: int,
        message: str,
        prefer_caption: bool,
        payment_id: object,
        order_id: object,
    ) -> str | None:
        edit_methods = (
            (
                ("caption", self.telegram_service.edit_message_caption),
                ("text", self.telegram_service.edit_message_text),
            )
            if prefer_caption
            else (
                ("text", self.telegram_service.edit_message_text),
                ("caption", self.telegram_service.edit_message_caption),
            )
        )
        for edit_type, edit_method in edit_methods:
            try:
                await edit_method(
                    chat_id,
                    message_id,
                    message,
                    reply_markup={"inline_keyboard": []},
                )
                return f"edited_{edit_type}"
            except TelegramDeliveryError as exc:
                if self._is_message_not_modified(exc):
                    return "already_finalized"
                logger.warning(
                    "manual_payment.seller_bot_edit_failed",
                    extra={
                        "payment_id": payment_id,
                        "order_id": order_id,
                        "edit_type": edit_type,
                        "error_type": type(exc).__name__,
                    },
                )
        return None

    async def _remove_seller_message_actions(
        self,
        *,
        chat_id: str,
        message_id: int,
        payment_id: object,
        order_id: object,
    ) -> None:
        try:
            await self.telegram_service.edit_message_reply_markup(
                chat_id,
                message_id,
                reply_markup={"inline_keyboard": []},
            )
        except TelegramDeliveryError as exc:
            if self._is_message_not_modified(exc):
                return
            logger.warning(
                "manual_payment.seller_bot_button_removal_failed",
                extra={
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "error_type": type(exc).__name__,
                },
            )
        else:
            logger.info(
                "manual_payment.seller_bot_buttons_removed",
                extra={
                    "payment_id": payment_id,
                    "order_id": order_id,
                },
            )

    @staticmethod
    def _is_message_not_modified(exc: TelegramDeliveryError) -> bool:
        return "message is not modified" in str(exc).lower()

    @staticmethod
    def _receipt_path(payload: Mapping[str, object]) -> str | None:
        value = payload.get("receipt_image_path")
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    def _final_payment_line(self, name: str, payload: Mapping[str, object]) -> str:
        if name == MANUAL_PAYMENT_APPROVED:
            return "✅ Оплата подтверждена"
        if name == MANUAL_PAYMENT_REJECTED:
            reason = payload.get("reject_reason") or "причина не указана"
            return f"❌ Оплата отклонена\nПричина: {reason}"
        return "⌛ Время оплаты истекло"


class ManualPaymentsService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        event_publisher: PaymentEventPublisher | None = None,
        audit_service: AuditService | NoopAuditService | None = None,
        uploads_service: UploadsService | None = None,
        storage: LocalStorageService | None = None,
        idempotency_service: IdempotencyService | None = None,
        now_factory=None,
    ) -> None:
        self.session = session
        self.repository = ManualPaymentsRepository(session)
        self.event_publisher = event_publisher
        self.outbox_service = None if event_publisher is not None else OutboxService(session)
        self.audit_service = audit_service or NoopAuditService()
        self.uploads_service = uploads_service or UploadsService(session)
        self.storage = storage or self.uploads_service.storage
        self.idempotency_service = idempotency_service or IdempotencyService(session)
        self.now_factory = now_factory or (lambda: datetime.now(UTC))
        self.in_app_notifications = notification_service_for_session(session)

    async def get_settings(self) -> SellerPaymentSettingsRead:
        payment_settings = await self.repository.get_settings()
        return self._settings_response(payment_settings)

    async def update_settings(
        self,
        payload: SellerPaymentSettingsUpdate,
        *,
        actor_user_id: int,
    ) -> SellerPaymentSettingsRead:
        payment_settings = await self.repository.get_settings()
        before_data = self._settings_audit_data(payment_settings)

        phone_e164 = payment_settings.seller_phone_e164 if payment_settings else None
        phone_display = payment_settings.seller_phone_display if payment_settings else None
        if payload.seller_phone is not None:
            try:
                phone_e164, phone_display = normalize_russian_phone(payload.seller_phone)
            except ValueError as exc:
                raise AppError(
                    "Invalid Russian payment phone number",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                ) from exc

        if payload.is_manual_sbp_enabled and not phone_e164:
            raise AppError(
                "Payment phone is required before manual SBP can be enabled",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        if payment_settings is None:
            payment_settings = SellerPaymentSettings(id=1)
            self.repository.add(payment_settings)

        payment_settings.is_manual_sbp_enabled = payload.is_manual_sbp_enabled
        payment_settings.seller_phone_e164 = phone_e164
        payment_settings.seller_phone_display = phone_display
        payment_settings.seller_bank_name = payload.seller_bank_name
        payment_settings.seller_recipient_name = payload.seller_recipient_name
        payment_settings.updated_by_user_id = actor_user_id
        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action="manual_payment.settings_updated",
            entity_type="seller_payment_settings",
            entity_id=1,
            before_data=before_data,
            after_data=self._settings_audit_data(payment_settings),
        )
        await self._commit("Payment settings update failed")
        await self._refresh_if_supported(payment_settings)
        return self._settings_response(payment_settings)

    async def create_for_checkout(
        self,
        order: Order,
        *,
        payment_settings: SellerPaymentSettings | None = None,
    ) -> ManualPayment:
        payment_settings = payment_settings or await self.require_checkout_settings()
        if order.total_amount <= Decimal("0.00"):
            raise AppError("Order total must be positive", status.HTTP_400_BAD_REQUEST)

        payment = ManualPayment(
            order_id=order.id,
            order=order,
            method=ManualPaymentMethod.SBP_PHONE,
            amount=order.total_amount,
            currency=ManualPaymentCurrency.RUB,
            seller_phone_e164=payment_settings.seller_phone_e164,
            seller_phone_display=payment_settings.seller_phone_display,
            seller_bank_name=payment_settings.seller_bank_name,
            seller_recipient_name=payment_settings.seller_recipient_name,
            payment_comment=f"Заказ #{order.id}",
            status=ManualPaymentStatus.PENDING,
            expires_at=self._now() + timedelta(minutes=PAYMENT_RESERVATION_MINUTES),
        )
        self.repository.add(payment)
        return payment

    async def require_checkout_settings(self) -> SellerPaymentSettings:
        payment_settings = await self.repository.get_settings()
        if (
            payment_settings is None
            or not payment_settings.is_manual_sbp_enabled
            or not payment_settings.seller_phone_e164
            or not payment_settings.seller_phone_display
        ):
            raise AppError(
                "Manual SBP payment is not configured",
                status.HTTP_409_CONFLICT,
            )
        return payment_settings

    async def get_for_customer(self, *, order_id: int, user_id: int) -> ManualPaymentRead:
        payment = await self.repository.get_for_order_owner(order_id=order_id, user_id=user_id)
        if payment is None:
            raise AppError("Payment not found", status.HTTP_404_NOT_FOUND)
        return self._payment_response(payment)

    async def submit(
        self,
        *,
        order_id: int,
        user_id: int,
        idempotency_key: str | None = None,
    ) -> ManualPaymentRead:
        idempotency_claim: IdempotencyClaim | None = None
        if idempotency_key:
            idempotency_claim = await self.idempotency_service.begin(
                user_id=user_id,
                scope="manual_payments.submit",
                key=idempotency_key,
                request_hash=IdempotencyService.hash_payload({"order_id": order_id}),
            )
            if idempotency_claim.replay_response is not None:
                return ManualPaymentRead.model_validate(idempotency_claim.replay_response)

        payment = await self.repository.get_for_order_owner(
            order_id=order_id,
            user_id=user_id,
            for_update=True,
        )
        if payment is None:
            raise AppError("Payment not found", status.HTTP_404_NOT_FOUND)

        now = self._now()
        if await self._expire_if_due(payment, now=now):
            payment_id = payment.id
            self._enqueue_event(MANUAL_PAYMENT_EXPIRED, payment)
            await self._commit("Payment expiration failed")
            payment = await self._reload_payment(payment_id)
            self._log_persisted(MANUAL_PAYMENT_EXPIRED, payment)
            await self._emit(MANUAL_PAYMENT_EXPIRED, payment)
            raise AppError("Payment has expired", status.HTTP_409_CONFLICT)
        if payment.status == ManualPaymentStatus.SUBMITTED:
            response = self._payment_response(payment, server_now=now)
            self.idempotency_service.complete(
                idempotency_claim,
                response_body=response.model_dump(mode="json"),
                response_status_code=status.HTTP_200_OK,
            )
            if idempotency_claim is not None:
                await self._commit("Payment submission idempotency update failed")
            return response
        if payment.status != ManualPaymentStatus.PENDING:
            raise AppError("Payment can no longer be submitted", status.HTTP_409_CONFLICT)

        payment.status = ManualPaymentStatus.SUBMITTED
        payment.submitted_at = payment.submitted_at or now
        await self.in_app_notifications.create_payment_status(payment, occurred_at=now)
        payment_id = payment.id
        response = self._payment_response(payment, server_now=now)
        self.idempotency_service.complete(
            idempotency_claim,
            response_body=response.model_dump(mode="json"),
            response_status_code=status.HTTP_200_OK,
        )
        self._enqueue_event(MANUAL_PAYMENT_SUBMITTED, payment)
        await self._commit("Payment submission failed")
        payment = await self._reload_payment(payment_id)
        self._log_persisted(MANUAL_PAYMENT_SUBMITTED, payment)
        response = self._payment_response(payment, server_now=now)
        await self._emit(MANUAL_PAYMENT_SUBMITTED, payment)
        return response

    async def upload_receipt(
        self,
        *,
        order_id: int,
        user_id: int,
        file: UploadFile,
        idempotency_key: str | None = None,
    ) -> ManualPaymentRead:
        upload = None
        idempotency_claim: IdempotencyClaim | None = None
        if idempotency_key:
            upload = await self.uploads_service.validate_and_read_image(file)
            idempotency_claim = await self.idempotency_service.begin(
                user_id=user_id,
                scope="manual_payments.receipt_upload",
                key=idempotency_key,
                request_hash=IdempotencyService.hash_payload(
                    {
                        "order_id": order_id,
                        "content_sha256": hashlib.sha256(upload.content).hexdigest(),
                        "extension": upload.extension,
                    }
                ),
            )
            if idempotency_claim.replay_response is not None:
                return ManualPaymentRead.model_validate(idempotency_claim.replay_response)

        payment = await self.repository.get_for_order_owner(
            order_id=order_id,
            user_id=user_id,
            for_update=True,
        )
        if payment is None:
            raise AppError("Payment not found", status.HTTP_404_NOT_FOUND)

        now = self._now()
        if await self._expire_if_due(payment, now=now):
            payment_id = payment.id
            self._enqueue_event(MANUAL_PAYMENT_EXPIRED, payment)
            await self._commit("Payment expiration failed")
            payment = await self._reload_payment(payment_id)
            self._log_persisted(MANUAL_PAYMENT_EXPIRED, payment)
            await self._emit(MANUAL_PAYMENT_EXPIRED, payment)
            raise AppError("Payment has expired", status.HTTP_409_CONFLICT)
        if payment.status not in ACTIVE_PAYMENT_STATUSES:
            raise AppError("Receipt can no longer be changed", status.HTTP_409_CONFLICT)

        payment_id = payment.id
        logger.info(
            "manual_payment.receipt_upload_started",
            extra={
                "payment_id": payment_id,
                "order_id": payment.order_id,
                "has_receipt_path": bool(payment.receipt_image_path),
            },
        )
        old_path = payment.receipt_image_path
        new_path: str | None = None
        committed = False
        try:
            if upload is None:
                upload = await self.uploads_service.validate_and_read_image(file)
            new_path = self.storage.save_bytes(
                upload.content,
                folder="payment_receipts",
                suffix=upload.extension,
            )
            logger.info(
                "manual_payment.receipt_upload_saved",
                extra={
                    "payment_id": payment_id,
                    "order_id": payment.order_id,
                    "has_receipt_path": True,
                },
            )
            try:
                await self.repository.update_receipt_image_path(
                    payment_id=payment_id,
                    receipt_image_path=new_path,
                )
                response = self._payment_response(payment, server_now=now)
                response.receipt_image_path = new_path
                response.receipt_image_url = settings.public_upload_url_for(new_path)
                self.idempotency_service.complete(
                    idempotency_claim,
                    response_body=response.model_dump(mode="json"),
                    response_status_code=status.HTTP_200_OK,
                )
                await self._commit("Payment receipt update failed")
            except AppError:
                raise
            except Exception as exc:
                await self.session.rollback()
                raise AppError(
                    "Payment receipt update failed",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                ) from exc
            committed = True
            payment = await self._reload_payment(payment_id)
            if payment.receipt_image_path != new_path:
                self.storage.delete(new_path)
                raise AppError(
                    "Receipt upload could not be confirmed",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        except Exception as exc:
            if new_path is not None and not committed:
                self.storage.delete(new_path)
            logger.warning(
                "manual_payment.receipt_upload_failed",
                extra={
                    "payment_id": payment_id,
                    "order_id": payment.order_id,
                    "has_receipt_path": bool(new_path),
                    "committed": committed,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        if old_path and old_path != new_path:
            try:
                self.storage.delete(old_path)
            except OSError:
                logger.warning(
                    "manual_payment.receipt_replaced_file_cleanup_failed",
                    extra={
                        "payment_id": payment_id,
                        "order_id": payment.order_id,
                        "has_receipt_path": True,
                    },
                )
        logger.info(
            "manual_payment.receipt_upload_persisted",
            extra={
                "payment_id": payment_id,
                "order_id": payment.order_id,
                "has_receipt_path": True,
            },
        )
        return self._payment_response(payment, server_now=now)

    async def list_for_seller(
        self,
        *,
        limit: int,
        offset: int,
        status_filter: ManualPaymentStatus | None = None,
    ) -> ManualPaymentList:
        payments = await self.repository.list_all(
            limit=limit,
            offset=offset,
            status=status_filter,
        )
        now = self._now()
        return ManualPaymentList(
            items=[self._payment_response(payment, server_now=now) for payment in payments]
        )

    async def get_for_seller(self, payment_id: int) -> ManualPaymentRead:
        payment = await self.repository.get_by_id(payment_id)
        if payment is None:
            raise AppError("Payment not found", status.HTTP_404_NOT_FOUND)
        return self._payment_response(payment)

    async def approve(
        self,
        payment_id: int,
        *,
        actor_user_id: int | None,
        source: str = "seller_panel",
        actor_telegram_user_id: int | None = None,
        seller_chat_id: int | None = None,
        seller_message_id: int | None = None,
    ) -> ManualPaymentRead:
        payment = await self.repository.get_by_id(payment_id, for_update=True)
        if payment is None:
            raise AppError("Payment not found", status.HTTP_404_NOT_FOUND)

        now = self._now()
        if payment.status == ManualPaymentStatus.APPROVED:
            return self._payment_response(payment, server_now=now)
        if await self._expire_if_due(payment, now=now):
            payment_id = payment.id
            self._enqueue_event(MANUAL_PAYMENT_EXPIRED, payment)
            await self._commit("Payment expiration failed")
            payment = await self._reload_payment(payment_id)
            self._log_persisted(MANUAL_PAYMENT_EXPIRED, payment)
            await self._emit(MANUAL_PAYMENT_EXPIRED, payment)
            raise AppError("Payment has expired", status.HTTP_409_CONFLICT)
        if payment.status not in ACTIVE_PAYMENT_STATUSES:
            raise AppError("Payment cannot be approved", status.HTTP_409_CONFLICT)

        before_status = payment.status
        previous_order_status = payment.order.status
        payment.status = ManualPaymentStatus.APPROVED
        payment.approved_at = now
        payment.approved_by_user_id = actor_user_id
        payment.order.status = OrderStatus.PROCESSING
        await self.in_app_notifications.create_payment_status(payment, occurred_at=now)
        if previous_order_status != payment.order.status:
            await self.in_app_notifications.create_order_status(payment.order, occurred_at=now)
        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action="manual_payment.approved",
            entity_type="manual_payment",
            entity_id=payment.id,
            before_data={"status": before_status.value},
            after_data={"status": payment.status.value, "order_status": payment.order.status.value},
            metadata={
                "source": source,
                "actor_telegram_user_id": actor_telegram_user_id,
            },
        )
        payment_id = payment.id
        self._enqueue_event(
            MANUAL_PAYMENT_APPROVED,
            payment,
            seller_chat_id=seller_chat_id,
            seller_message_id=seller_message_id,
        )
        await self._commit("Payment approval failed")
        payment = await self._reload_payment(payment_id)
        self._log_persisted(MANUAL_PAYMENT_APPROVED, payment)
        response = self._payment_response(payment, server_now=now)
        await self._emit(
            MANUAL_PAYMENT_APPROVED,
            payment,
            seller_chat_id=seller_chat_id,
            seller_message_id=seller_message_id,
        )
        return response

    async def reject(
        self,
        payment_id: int,
        *,
        actor_user_id: int | None,
        reject_reason: str | None = None,
        source: str = "seller_panel",
        actor_telegram_user_id: int | None = None,
        seller_chat_id: int | None = None,
        seller_message_id: int | None = None,
    ) -> ManualPaymentRead:
        payment = await self.repository.get_by_id(payment_id, for_update=True)
        if payment is None:
            raise AppError("Payment not found", status.HTTP_404_NOT_FOUND)

        now = self._now()
        if payment.status == ManualPaymentStatus.REJECTED:
            return self._payment_response(payment, server_now=now)
        if await self._expire_if_due(payment, now=now):
            payment_id = payment.id
            self._enqueue_event(MANUAL_PAYMENT_EXPIRED, payment)
            await self._commit("Payment expiration failed")
            payment = await self._reload_payment(payment_id)
            self._log_persisted(MANUAL_PAYMENT_EXPIRED, payment)
            await self._emit(MANUAL_PAYMENT_EXPIRED, payment)
            raise AppError("Payment has expired", status.HTTP_409_CONFLICT)
        if payment.status not in ACTIVE_PAYMENT_STATUSES:
            raise AppError("Payment cannot be rejected", status.HTTP_409_CONFLICT)

        before_status = payment.status
        previous_order_status = payment.order.status
        payment.status = ManualPaymentStatus.REJECTED
        payment.rejected_at = now
        payment.rejected_by_user_id = actor_user_id
        payment.reject_reason = reject_reason
        payment.order.status = OrderStatus.CANCELLED
        await self.in_app_notifications.create_payment_status(payment, occurred_at=now)
        if previous_order_status != payment.order.status:
            await self.in_app_notifications.create_order_status(payment.order, occurred_at=now)
        await self._release_stock(payment, now=now)
        await self.audit_service.record_action(
            actor_user_id=actor_user_id,
            action="manual_payment.rejected",
            entity_type="manual_payment",
            entity_id=payment.id,
            before_data={"status": before_status.value},
            after_data={
                "status": payment.status.value,
                "order_status": payment.order.status.value,
                "reject_reason": reject_reason,
            },
            metadata={
                "source": source,
                "actor_telegram_user_id": actor_telegram_user_id,
            },
        )
        payment_id = payment.id
        self._enqueue_event(
            MANUAL_PAYMENT_REJECTED,
            payment,
            seller_chat_id=seller_chat_id,
            seller_message_id=seller_message_id,
        )
        await self._commit("Payment rejection failed")
        payment = await self._reload_payment(payment_id)
        self._log_persisted(MANUAL_PAYMENT_REJECTED, payment)
        response = self._payment_response(payment, server_now=now)
        await self._emit(
            MANUAL_PAYMENT_REJECTED,
            payment,
            seller_chat_id=seller_chat_id,
            seller_message_id=seller_message_id,
        )
        return response

    async def expire_due_payment(self, payment_id: int) -> bool:
        payment = await self.repository.get_by_id(payment_id, for_update=True)
        if payment is None or payment.status not in ACTIVE_PAYMENT_STATUSES:
            return False
        now = self._now()
        if payment.expires_at > now:
            return False
        await self._mark_expired(payment, now=now)
        payment_id = payment.id
        self._enqueue_event(MANUAL_PAYMENT_EXPIRED, payment)
        await self._commit("Payment expiration failed")
        payment = await self._reload_payment(payment_id)
        self._log_persisted(MANUAL_PAYMENT_EXPIRED, payment)
        await self._emit(MANUAL_PAYMENT_EXPIRED, payment)
        return True

    async def expire_due_batch(self, *, limit: int = 100) -> int:
        payment_ids = await self.repository.list_due_ids(now=self._now(), limit=limit)
        expired_count = 0
        for payment_id in payment_ids:
            if await self.expire_due_payment(payment_id):
                expired_count += 1
        return expired_count

    async def actor_user_id_for_telegram(self, telegram_id: int) -> int | None:
        user = await self.repository.get_user_by_telegram_id(telegram_id)
        if (
            user is None
            or not user.is_active
            or user.role not in {UserRole.SELLER, UserRole.ADMIN}
        ):
            return None
        return user.id

    async def _expire_if_due(self, payment: ManualPayment, *, now: datetime) -> bool:
        if payment.status not in ACTIVE_PAYMENT_STATUSES or payment.expires_at > now:
            return False
        await self._mark_expired(payment, now=now)
        return True

    async def _mark_expired(self, payment: ManualPayment, *, now: datetime) -> None:
        previous_order_status = payment.order.status
        payment.status = ManualPaymentStatus.EXPIRED
        payment.order.status = OrderStatus.CANCELLED
        await self.in_app_notifications.create_payment_status(payment, occurred_at=now)
        if previous_order_status != payment.order.status:
            await self.in_app_notifications.create_order_status(payment.order, occurred_at=now)
        await self._release_stock(payment, now=now)

    async def _release_stock(self, payment: ManualPayment, *, now: datetime) -> None:
        if payment.stock_released_at is not None:
            return
        variants = await self.repository.lock_variants_by_ids(
            item.product_variant_id for item in payment.order.items
        )
        for item in payment.order.items:
            variant = variants.get(item.product_variant_id)
            if variant is None:
                raise AppError("Reserved product variant not found", status.HTTP_409_CONFLICT)
            variant.stock_quantity += item.quantity
        payment.stock_released_at = now

    async def _emit(
        self,
        name: str,
        payment: ManualPayment,
        *,
        seller_chat_id: int | None = None,
        seller_message_id: int | None = None,
    ) -> None:
        if self.outbox_service is not None:
            return
        payload = self._event_payload(payment)
        if seller_chat_id is not None:
            payload["seller_telegram_chat_id"] = seller_chat_id
        if seller_message_id is not None:
            payload["seller_telegram_message_id"] = seller_message_id
        try:
            assert self.event_publisher is not None
            await self.event_publisher.emit(name, payload)
        except Exception as exc:
            if name == MANUAL_PAYMENT_SUBMITTED:
                logger.warning(
                    "manual_payment.seller_bot_notification_failed",
                    extra={
                        "payment_id": payment.id,
                        "order_id": payment.order_id,
                        "status": payment.status.value,
                        "error_type": type(exc).__name__,
                    },
                )
            else:
                logger.warning(
                    "Failed to process post-commit payment event %s",
                    name,
                    exc_info=True,
                )
            try:
                await self.session.rollback()
            except Exception:
                logger.warning("Failed to reset payment event session", exc_info=True)

    def _enqueue_event(
        self,
        name: str,
        payment: ManualPayment,
        *,
        seller_chat_id: int | None = None,
        seller_message_id: int | None = None,
    ) -> None:
        if self.outbox_service is None:
            return
        payload = self._event_payload(payment)
        if seller_chat_id is not None:
            payload["seller_telegram_chat_id"] = seller_chat_id
        if seller_message_id is not None:
            payload["seller_telegram_message_id"] = seller_message_id
        consumers = (
            (SELLER_CONSUMER,)
            if name == MANUAL_PAYMENT_SUBMITTED
            else (SELLER_CONSUMER, CUSTOMER_CONSUMER)
        )
        self.outbox_service.enqueue(
            event_name=name,
            aggregate_type="manual_payment",
            aggregate_id=payment.id,
            payload=payload,
            consumers=consumers,
        )

    def _event_payload(self, payment: ManualPayment) -> dict[str, object]:
        order = payment.order
        return {
            "payment_id": payment.id,
            "order_id": order.id,
            "order_number": order.order_number,
            "user_id": order.user_id,
            "customer_username": order.user.username if order.user is not None else None,
            "customer_phone": order.contact_phone,
            "delivery_method": (
                order.delivery_method.value if order.delivery_method is not None else None
            ),
            "delivery_method_label": delivery_method_label(order.delivery_method),
            "delivery_price": str(order.delivery_price),
            "amount": str(payment.amount),
            "payment_comment": payment.payment_comment,
            "expires_at": payment.expires_at.isoformat(),
            "has_receipt": bool(payment.receipt_image_path),
            "receipt_image_path": payment.receipt_image_path,
            "reject_reason": payment.reject_reason,
            "status": payment.status.value,
            "seller_telegram_chat_id": payment.seller_telegram_chat_id,
            "seller_telegram_message_id": payment.seller_telegram_message_id,
        }

    def _payment_response(
        self,
        payment: ManualPayment,
        *,
        server_now: datetime | None = None,
    ) -> ManualPaymentRead:
        receipt_url = None
        if payment.receipt_image_path:
            receipt_url = settings.public_upload_url_for(payment.receipt_image_path)
        order = payment.order
        return ManualPaymentRead(
            id=payment.id,
            order_id=payment.order_id,
            order_number=order.order_number,
            order_status=order.status,
            customer_user_id=order.user_id,
            customer_name=order.contact_name,
            customer_phone=order.contact_phone,
            delivery_method=order.delivery_method,
            delivery_price=order.delivery_price,
            method=payment.method,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status,
            expires_at=payment.expires_at,
            server_now=server_now or self._now(),
            seller_phone_display=payment.seller_phone_display,
            seller_phone_e164=payment.seller_phone_e164,
            seller_bank_name=payment.seller_bank_name,
            seller_recipient_name=payment.seller_recipient_name,
            payment_comment=payment.payment_comment,
            receipt_image_path=payment.receipt_image_path,
            receipt_image_url=receipt_url,
            submitted_at=payment.submitted_at,
            approved_at=payment.approved_at,
            rejected_at=payment.rejected_at,
            reject_reason=payment.reject_reason,
            stock_released_at=payment.stock_released_at,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )

    async def _reload_payment(self, payment_id: int) -> ManualPayment:
        payment = await self.repository.get_by_id(
            payment_id,
            populate_existing=True,
        )
        if payment is None:
            raise RuntimeError(f"Manual payment {payment_id} disappeared after commit")
        return payment

    @staticmethod
    def _log_persisted(event_name: str, payment: ManualPayment) -> None:
        logger.info(
            event_name,
            extra={
                "payment_id": payment.id,
                "order_id": payment.order_id,
                "status": payment.status.value,
            },
        )

    def _settings_response(
        self,
        payment_settings: SellerPaymentSettings | None,
    ) -> SellerPaymentSettingsRead:
        if payment_settings is None:
            return SellerPaymentSettingsRead(is_manual_sbp_enabled=False)
        return SellerPaymentSettingsRead(
            is_manual_sbp_enabled=payment_settings.is_manual_sbp_enabled,
            seller_phone_e164=payment_settings.seller_phone_e164,
            seller_phone_display=payment_settings.seller_phone_display,
            seller_bank_name=payment_settings.seller_bank_name,
            seller_recipient_name=payment_settings.seller_recipient_name,
            updated_at=payment_settings.updated_at,
        )

    def _settings_audit_data(
        self,
        payment_settings: SellerPaymentSettings | None,
    ) -> dict[str, object] | None:
        if payment_settings is None:
            return None
        return {
            "is_manual_sbp_enabled": payment_settings.is_manual_sbp_enabled,
            "seller_phone_e164": payment_settings.seller_phone_e164,
            "seller_phone_display": payment_settings.seller_phone_display,
            "seller_bank_name": payment_settings.seller_bank_name,
            "seller_recipient_name": payment_settings.seller_recipient_name,
        }

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc
        except Exception:
            await self.session.rollback()
            raise

    async def _refresh_if_supported(self, instance: object) -> None:
        refresh = getattr(self.session, "refresh", None)
        if callable(refresh):
            await refresh(instance)

    def _now(self) -> datetime:
        return self.now_factory()


def _seller_panel_payment_url(payment_id: int) -> str:
    return join_public_url(
        settings.public_seller_panel_base_url,
        f"orders?payment={payment_id}",
    )
