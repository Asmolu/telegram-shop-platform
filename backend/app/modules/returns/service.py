from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from secrets import token_hex
from typing import Protocol

from fastapi import UploadFile, status
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ReturnRequest,
    ReturnRequestAttachment,
    ReturnRequestItem,
    ReturnRequestStatus,
)
from app.modules.returns.repository import ReturnsRepository
from app.modules.returns.schemas import (
    ReturnDecisionRequest,
    ReturnEligibilityItemRead,
    ReturnEligibilityRead,
    ReturnRequestCreate,
    ReturnRequestList,
    ReturnRequestRead,
)
from app.modules.returns.telegram_notifications import (
    build_return_attachment_caption,
    build_return_request_action_reply_markup,
    build_return_request_notification_message,
)
from app.modules.telegram.service import TelegramDeliveryError, TelegramService
from app.modules.uploads.storage import LocalStorageService

logger = logging.getLogger(__name__)

RETURN_WINDOW_DAYS = 14
RETURN_WINDOW = timedelta(days=RETURN_WINDOW_DAYS)
MAX_RETURN_ATTACHMENTS = 5
MAX_RETURN_ATTACHMENT_SIZE_BYTES = 20 * 1024 * 1024
RETURN_CREATED_MESSAGE = "Заявка отправлена. Продавец свяжется с вами."

RETURN_ATTACHMENT_TYPES: dict[str, tuple[set[str], str]] = {
    "image/jpeg": ({".jpg", ".jpeg"}, "image"),
    "image/png": ({".png"}, "image"),
    "image/webp": ({".webp"}, "image"),
    "video/mp4": ({".mp4"}, "video"),
    "video/webm": ({".webm"}, "video"),
    "video/quicktime": ({".mov", ".qt"}, "video"),
}


class ReturnSellerNotifier(Protocol):
    async def notify_return_request_created(self, return_request: ReturnRequest) -> None:
        """Deliver a seller-facing notification after the return request is committed."""


class TelegramReturnSellerNotifier:
    def __init__(
        self,
        *,
        telegram_service: TelegramService | None = None,
        chat_id: str | None = None,
        storage: LocalStorageService | None = None,
    ) -> None:
        self.chat_id = chat_id or settings.telegram_returns_notification_chat_id
        self.telegram_service = telegram_service or TelegramService(
            seller_chat_id=self.chat_id or ""
        )
        self.storage = storage or LocalStorageService()

    async def notify_return_request_created(self, return_request: ReturnRequest) -> None:
        bot_token = getattr(self.telegram_service, "bot_token", settings.telegram_bot_token)
        chat_id = self.chat_id
        if not bot_token or not chat_id:
            return

        message_id = await self._send_text_notification(chat_id, return_request)
        await self._send_media_attachments(
            chat_id,
            return_request,
            reply_to_message_id=message_id,
        )

    async def _send_text_notification(
        self,
        chat_id: str,
        return_request: ReturnRequest,
    ) -> int | None:
        try:
            return await self.telegram_service.send_message(
                chat_id,
                build_return_request_notification_message(return_request),
                reply_markup=build_return_request_action_reply_markup(return_request.id),
            )
        except TelegramDeliveryError:
            logger.warning(
                "returns.seller_notification_text_delivery_failed",
                exc_info=True,
                extra={
                    "return_request_id": return_request.id,
                    "order_id": return_request.order_id,
                },
            )
        except Exception:
            logger.warning(
                "returns.seller_notification_text_failed",
                exc_info=True,
                extra={
                    "return_request_id": return_request.id,
                    "order_id": return_request.order_id,
                },
            )
        return None

    async def _send_media_attachments(
        self,
        chat_id: str,
        return_request: ReturnRequest,
        *,
        reply_to_message_id: int | None,
    ) -> None:
        caption = build_return_attachment_caption(return_request)
        attachments = sorted(
            return_request.attachments,
            key=lambda attachment: attachment.position,
        )
        for attachment in attachments:
            allowed = RETURN_ATTACHMENT_TYPES.get(attachment.mime_type)
            if allowed is None:
                logger.warning(
                    "returns.seller_notification_attachment_unsupported",
                    extra={
                        "return_request_id": return_request.id,
                        "attachment_id": attachment.id,
                        "media_type": attachment.media_type,
                        "mime_type": attachment.mime_type,
                    },
                )
                continue

            try:
                content = self.storage.read_bytes(attachment.file_path)
            except OSError:
                logger.warning(
                    "returns.seller_notification_attachment_read_failed",
                    exc_info=True,
                    extra={
                        "return_request_id": return_request.id,
                        "attachment_id": attachment.id,
                        "media_type": attachment.media_type,
                        "mime_type": attachment.mime_type,
                        "has_file_path": bool(attachment.file_path),
                    },
                )
                continue

            filename = _telegram_attachment_filename(attachment)
            try:
                if attachment.media_type == "image":
                    await self.telegram_service.send_photo_bytes(
                        chat_id,
                        content,
                        filename=filename,
                        mime_type=attachment.mime_type,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                    )
                else:
                    await self.telegram_service.send_video_bytes(
                        chat_id,
                        content,
                        filename=filename,
                        mime_type=attachment.mime_type,
                        caption=caption,
                        reply_to_message_id=reply_to_message_id,
                    )
            except TelegramDeliveryError:
                logger.warning(
                    "returns.seller_notification_attachment_delivery_failed",
                    exc_info=True,
                    extra={
                        "return_request_id": return_request.id,
                        "attachment_id": attachment.id,
                        "media_type": attachment.media_type,
                        "mime_type": attachment.mime_type,
                    },
                )
            except Exception:
                logger.warning(
                    "returns.seller_notification_attachment_failed",
                    exc_info=True,
                    extra={
                        "return_request_id": return_request.id,
                        "attachment_id": attachment.id,
                        "media_type": attachment.media_type,
                        "mime_type": attachment.mime_type,
                    },
                )


class ReturnsService:
    def __init__(
        self,
        session,
        *,
        storage: LocalStorageService | None = None,
        seller_notifier: ReturnSellerNotifier | None = None,
        now_factory=None,
    ) -> None:
        self.session = session
        self.repository = ReturnsRepository(session)
        self.storage = storage or LocalStorageService()
        self.seller_notifier = seller_notifier or TelegramReturnSellerNotifier()
        self.now_factory = now_factory or (lambda: datetime.now(UTC))

    async def get_return_eligibility(
        self,
        *,
        order_id: int,
        user_id: int,
    ) -> ReturnEligibilityRead:
        order = await self.repository.get_order_for_user(order_id=order_id, user_id=user_id)
        if order is None:
            raise AppError("Order not found", status.HTTP_404_NOT_FOUND)
        existing_request = await self.repository.get_return_for_order(order.id)
        return self._build_eligibility(order, existing_request=existing_request)

    async def create_return_request(
        self,
        *,
        order_id: int,
        user_id: int,
        payload: ReturnRequestCreate,
        files: Iterable[UploadFile] | None = None,
    ) -> ReturnRequestRead:
        order = await self.repository.get_order_for_user(
            order_id=order_id,
            user_id=user_id,
            for_update=True,
        )
        if order is None:
            raise AppError("Order not found", status.HTTP_404_NOT_FOUND)

        existing_request = await self.repository.get_return_for_order(order.id)
        selected_items = self._validate_create_payload(
            order,
            payload=payload,
            existing_request=existing_request,
        )
        attachments = await self._validate_attachments(list(files or []))

        return_request = ReturnRequest(
            return_number=self._generate_return_number(),
            order_id=order.id,
            user_id=user_id,
            status=ReturnRequestStatus.PENDING,
            reason=payload.reason,
            comment=payload.comment,
            items=[
                self._snapshot_item(order_item, quantity=quantity)
                for order_item, quantity in selected_items
            ],
            attachments=[],
        )
        self.repository.add(return_request)

        saved_paths: list[str] = []
        committed = False
        try:
            await self._flush()
            for position, attachment in enumerate(attachments):
                file_path = self.storage.save_bytes(
                    attachment.content,
                    folder="returns",
                    suffix=attachment.extension,
                )
                saved_paths.append(file_path)
                return_request.attachments.append(
                    ReturnRequestAttachment(
                        file_path=file_path,
                        original_filename=attachment.original_filename,
                        mime_type=attachment.mime_type,
                        size_bytes=attachment.size_bytes,
                        media_type=attachment.media_type,
                        position=position,
                    )
                )
            return_request_id = return_request.id
            await self._commit("Return request create failed")
            committed = True
        except AppError:
            await self._rollback_and_delete(saved_paths, committed=committed)
            raise
        except IntegrityError as exc:
            await self._rollback_and_delete(saved_paths, committed=committed)
            raise AppError(
                "Return request already exists for this order",
                status.HTTP_409_CONFLICT,
            ) from exc
        except Exception as exc:
            await self._rollback_and_delete(saved_paths, committed=committed)
            raise AppError(
                "Return request create failed",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exc

        created = await self.repository.get_by_id(return_request_id)
        if created is None:
            raise AppError("Return request not found", status.HTTP_404_NOT_FOUND)
        await self._notify_seller(created)
        return ReturnRequestRead.model_validate(created).model_copy(
            update={"message": RETURN_CREATED_MESSAGE}
        )

    async def list_admin_return_requests(
        self,
        *,
        limit: int,
        offset: int,
        status_filter: ReturnRequestStatus | None = None,
        order_id: int | None = None,
        user_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> ReturnRequestList:
        items = await self.repository.list_all(
            limit=limit,
            offset=offset,
            status=status_filter,
            order_id=order_id,
            user_id=user_id,
            created_from=created_from,
            created_to=created_to,
        )
        return ReturnRequestList(items=[ReturnRequestRead.model_validate(item) for item in items])

    async def get_admin_return_request(self, return_request_id: int) -> ReturnRequestRead:
        return_request = await self.repository.get_by_id(return_request_id)
        if return_request is None:
            raise AppError("Return request not found", status.HTTP_404_NOT_FOUND)
        return ReturnRequestRead.model_validate(return_request)

    async def approve(
        self,
        *,
        return_request_id: int,
        actor_user_id: int,
        payload: ReturnDecisionRequest,
    ) -> ReturnRequestRead:
        return await self._decide(
            return_request_id=return_request_id,
            actor_user_id=actor_user_id,
            payload=payload,
            next_status=ReturnRequestStatus.APPROVED,
        )

    async def reject(
        self,
        *,
        return_request_id: int,
        actor_user_id: int,
        payload: ReturnDecisionRequest,
    ) -> ReturnRequestRead:
        return await self._decide(
            return_request_id=return_request_id,
            actor_user_id=actor_user_id,
            payload=payload,
            next_status=ReturnRequestStatus.REJECTED,
        )

    async def _decide(
        self,
        *,
        return_request_id: int,
        actor_user_id: int,
        payload: ReturnDecisionRequest,
        next_status: ReturnRequestStatus,
    ) -> ReturnRequestRead:
        return_request = await self.repository.get_by_id(return_request_id, for_update=True)
        if return_request is None:
            raise AppError("Return request not found", status.HTTP_404_NOT_FOUND)
        if return_request.status != ReturnRequestStatus.PENDING:
            raise AppError("Return request is already decided", status.HTTP_409_CONFLICT)

        return_request.status = next_status
        return_request.decided_at = self._now()
        return_request.decided_by_user_id = actor_user_id
        return_request.decision_comment = payload.decision_comment
        await self._commit("Return request decision failed")

        updated = await self.repository.get_by_id(return_request_id)
        if updated is None:
            raise AppError("Return request not found", status.HTTP_404_NOT_FOUND)
        return ReturnRequestRead.model_validate(updated)

    def _build_eligibility(
        self,
        order: Order,
        *,
        existing_request: ReturnRequest | None,
    ) -> ReturnEligibilityRead:
        now = self._now()
        return_window_until = self._return_window_until(order)
        reason_code: str | None = None
        message = "Order is eligible for return"

        if existing_request is not None:
            reason_code = "return_request_exists"
            message = "Return request already exists for this order"
        elif order.status != OrderStatus.DELIVERED:
            reason_code = "order_not_delivered"
            message = "Returns are available only after delivery"
        elif return_window_until is None or now > return_window_until:
            reason_code = "return_window_expired"
            message = "Return window has expired"

        items = [
            self._eligibility_item(order_item, order_block_reason=reason_code)
            for order_item in order.items
        ]
        has_eligible_item = any(item.eligible for item in items)
        eligible = reason_code is None and has_eligible_item
        if reason_code is None and not has_eligible_item:
            reason_code = "no_returnable_items"
            message = "Order has no returnable items"

        return ReturnEligibilityRead(
            eligible=eligible,
            reason_code=reason_code,
            message=message,
            return_window_until=return_window_until,
            order_id=order.id,
            return_request_id=existing_request.id if existing_request is not None else None,
            items=items,
        )

    def _eligibility_item(
        self,
        order_item: OrderItem,
        *,
        order_block_reason: str | None,
    ) -> ReturnEligibilityItemRead:
        product = getattr(order_item, "product", None)
        ineligible_reason = order_block_reason
        if ineligible_reason is None and not order_item.is_returnable:
            ineligible_reason = "non_returnable"
        return ReturnEligibilityItemRead(
            order_item_id=order_item.id,
            product_name=order_item.product_name,
            product_brand=getattr(product, "brand", None),
            image_url=_product_image_url(product),
            sku=order_item.variant_sku,
            size=order_item.variant_size,
            color=order_item.variant_color,
            quantity=order_item.quantity,
            is_returnable=order_item.is_returnable,
            eligible=ineligible_reason is None,
            ineligible_reason=ineligible_reason,
        )

    def _validate_create_payload(
        self,
        order: Order,
        *,
        payload: ReturnRequestCreate,
        existing_request: ReturnRequest | None,
    ) -> list[tuple[OrderItem, int]]:
        eligibility = self._build_eligibility(order, existing_request=existing_request)
        if existing_request is not None:
            raise AppError(
                "Return request already exists for this order",
                status.HTTP_409_CONFLICT,
            )
        if order.status != OrderStatus.DELIVERED:
            raise AppError("Returns are available only after delivery", status.HTTP_400_BAD_REQUEST)
        if not eligibility.eligible:
            raise AppError(eligibility.message, status.HTTP_400_BAD_REQUEST)
        if not payload.items:
            raise AppError("At least one item must be selected", status.HTTP_400_BAD_REQUEST)

        order_items_by_id = {item.id: item for item in order.items}
        selected_items: list[tuple[OrderItem, int]] = []
        for selected in payload.items:
            order_item = order_items_by_id.get(selected.order_item_id)
            if order_item is None:
                raise AppError(
                    "Return item does not belong to this order",
                    status.HTTP_400_BAD_REQUEST,
                )
            if not order_item.is_returnable:
                raise AppError("Order item is not returnable", status.HTTP_400_BAD_REQUEST)
            if selected.quantity > order_item.quantity:
                raise AppError(
                    "Return quantity exceeds purchased quantity",
                    status.HTTP_400_BAD_REQUEST,
                )
            selected_items.append((order_item, selected.quantity))
        return selected_items

    def _snapshot_item(self, order_item: OrderItem, *, quantity: int) -> ReturnRequestItem:
        product = getattr(order_item, "product", None)
        return ReturnRequestItem(
            order_item_id=order_item.id,
            product_id=order_item.product_id,
            product_variant_id=order_item.product_variant_id,
            product_name=order_item.product_name,
            product_brand=getattr(product, "brand", None),
            sku=order_item.variant_sku,
            size=order_item.variant_size,
            color=order_item.variant_color,
            unit_price=order_item.unit_price,
            quantity=quantity,
        )

    async def _validate_attachments(
        self,
        files: list[UploadFile],
    ) -> list[ValidatedReturnAttachment]:
        if len(files) > MAX_RETURN_ATTACHMENTS:
            raise AppError("Too many return attachments", status.HTTP_400_BAD_REQUEST)
        attachments: list[ValidatedReturnAttachment] = []
        for file in files:
            original_filename = _safe_original_filename(file.filename)
            extension = Path(original_filename).suffix.lower()
            mime_type = file.content_type or ""
            allowed = RETURN_ATTACHMENT_TYPES.get(mime_type)
            if allowed is None:
                raise AppError("Invalid MIME type", status.HTTP_400_BAD_REQUEST)
            allowed_extensions, media_type = allowed
            if extension not in allowed_extensions:
                raise AppError("Invalid file extension", status.HTTP_400_BAD_REQUEST)
            content = await file.read(MAX_RETURN_ATTACHMENT_SIZE_BYTES + 1)
            if len(content) > MAX_RETURN_ATTACHMENT_SIZE_BYTES:
                raise AppError("File size exceeds limit", status.HTTP_400_BAD_REQUEST)
            if not content:
                raise AppError("Uploaded file is empty", status.HTTP_400_BAD_REQUEST)
            attachments.append(
                ValidatedReturnAttachment(
                    content=content,
                    extension=extension,
                    original_filename=original_filename,
                    mime_type=mime_type,
                    media_type=media_type,
                    size_bytes=len(content),
                )
            )
        return attachments

    def _return_window_until(self, order: Order) -> datetime | None:
        if order.status != OrderStatus.DELIVERED:
            return None
        start = order.delivered_at or order.created_at
        if start is None:
            return None
        return _as_utc(start) + RETURN_WINDOW

    def _generate_return_number(self) -> str:
        return f"RET-{token_hex(6).upper()}"

    def _now(self) -> datetime:
        return _as_utc(self.now_factory())

    async def _flush(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError:
            raise
        except Exception as exc:
            raise AppError("Return request create failed", status.HTTP_409_CONFLICT) from exc

    async def _commit(self, error_message: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise
        except Exception as exc:
            await self.session.rollback()
            raise AppError(error_message, status.HTTP_409_CONFLICT) from exc

    async def _rollback_and_delete(self, paths: list[str], *, committed: bool) -> None:
        if not committed:
            await self.session.rollback()
        for path in paths:
            self.storage.delete(path)

    async def _notify_seller(self, return_request: ReturnRequest) -> None:
        try:
            await self.seller_notifier.notify_return_request_created(return_request)
        except TelegramDeliveryError:
            logger.warning(
                "returns.seller_notification_delivery_failed",
                exc_info=True,
                extra={
                    "return_request_id": return_request.id,
                    "order_id": return_request.order_id,
                },
            )
        except Exception:
            logger.warning(
                "returns.seller_notification_failed",
                exc_info=True,
                extra={
                    "return_request_id": return_request.id,
                    "order_id": return_request.order_id,
                },
            )


@dataclass(frozen=True)
class ValidatedReturnAttachment:
    content: bytes
    extension: str
    original_filename: str
    mime_type: str
    media_type: str
    size_bytes: int


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _product_image_url(product: Product | None) -> str | None:
    if product is None:
        return None
    try:
        return product.thumbnail_image_url or product.image_url
    except Exception:
        return None


def _telegram_attachment_filename(attachment: ReturnRequestAttachment) -> str:
    original_filename = _safe_original_filename(attachment.original_filename)
    if Path(original_filename).suffix:
        return original_filename
    stored_suffix = Path(attachment.file_path).suffix
    if stored_suffix:
        return f"{original_filename}{stored_suffix}"
    return f"return-attachment-{attachment.id or 'file'}"


def _safe_original_filename(filename: str | None) -> str:
    if not filename:
        return "upload"
    basename = PureWindowsPath(PurePosixPath(filename).name).name
    return basename.replace("\x00", "").strip()[:255] or "upload"
