from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from app.common.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    Order,
    OrderDeliveryMethod,
    OrderItem,
    OrderStatus,
    Product,
    ProductImage,
    ProductSizeGrid,
    ProductSizeGroup,
    ProductStatus,
    ProductVariant,
    ReturnRefund,
    ReturnRefundStatus,
    ReturnRequest,
    ReturnRequestAttachment,
    ReturnRequestItem,
    ReturnRequestStatus,
    User,
    UserRole,
)
from app.main import create_app
from app.modules.returns.router import get_returns_service
from app.modules.returns.schemas import (
    ReturnDecisionRequest,
    ReturnLifecycleCommentRequest,
    ReturnProcessRequest,
    ReturnRequestCreate,
    ReturnRequestItemCreate,
)
from app.modules.returns.service import (
    MAX_RETURN_ATTACHMENT_SIZE_BYTES,
    ReturnsService,
    TelegramReturnSellerNotifier,
)
from app.modules.telegram.service import TelegramDeliveryError

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


class DummySession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


class FakeStorage:
    def __init__(self, *, fail_save: bool = False) -> None:
        self.fail_save = fail_save
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.next_id = 1

    def save_bytes(self, content: bytes, *, folder: str, suffix: str) -> str:
        if self.fail_save:
            raise OSError("storage unavailable")
        path = f"{folder}/return-{self.next_id}{suffix}"
        self.next_id += 1
        self.saved[path] = content
        return path

    def delete(self, relative_path: str) -> None:
        self.deleted.append(relative_path)
        self.saved.pop(relative_path, None)

    def read_bytes(self, relative_path: str) -> bytes:
        if ".." in relative_path.replace("\\", "/").split("/"):
            raise FileNotFoundError(relative_path)
        try:
            return self.saved[relative_path]
        except KeyError as exc:
            raise FileNotFoundError(relative_path) from exc


class FakeReturnNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.session: DummySession | None = None
        self.requests: list[ReturnRequest] = []
        self.commit_counts: list[int] = []

    async def notify_return_request_created(self, return_request: ReturnRequest) -> None:
        if self.session is not None:
            self.commit_counts.append(self.session.commit_count)
        if self.fail:
            raise RuntimeError("telegram unavailable")
        self.requests.append(return_request)


class FakeUserBlocksService:
    def __init__(self, *, blocked_user_ids: set[int] | None = None) -> None:
        self.blocked_user_ids = blocked_user_ids or set()

    async def assert_user_not_blocked(self, user_id: int) -> None:
        if user_id in self.blocked_user_ids:
            raise AppError("Ваш аккаунт ограничен. Свяжитесь с продавцом.", 403)


class FakeTelegramService:
    bot_token = "token"
    seller_chat_id = "seller-chat"

    def __init__(
        self,
        *,
        fail_message: bool = False,
        fail_photo: bool = False,
        fail_video: bool = False,
    ) -> None:
        self.fail_message = fail_message
        self.fail_photo = fail_photo
        self.fail_video = fail_video
        self.sent_messages: list[tuple[str, str, dict[str, object] | None]] = []
        self.photos: list[tuple[str, bytes, str, str, str | None, int | None]] = []
        self.videos: list[tuple[str, bytes, str, str, str | None, int | None]] = []

    async def send_message(
        self,
        chat_id: str,
        message: str,
        *,
        reply_markup: dict[str, object] | None = None,
        **_kwargs,
    ) -> int:
        if self.fail_message:
            raise TelegramDeliveryError("sendMessage failed")
        self.sent_messages.append((chat_id, message, reply_markup))
        return 101

    async def send_photo_bytes(
        self,
        chat_id: str,
        photo: bytes,
        *,
        filename: str,
        mime_type: str,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        **_kwargs,
    ) -> int:
        if self.fail_photo:
            raise TelegramDeliveryError("sendPhoto failed")
        self.photos.append((chat_id, photo, filename, mime_type, caption, reply_to_message_id))
        return 201

    async def send_video_bytes(
        self,
        chat_id: str,
        video: bytes,
        *,
        filename: str,
        mime_type: str,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        **_kwargs,
    ) -> int:
        if self.fail_video:
            raise TelegramDeliveryError("sendVideo failed")
        self.videos.append((chat_id, video, filename, mime_type, caption, reply_to_message_id))
        return 301


class FakeReturnsRepository:
    def __init__(self) -> None:
        self.orders: dict[int, Order] = {}
        self.return_requests: dict[int, ReturnRequest] = {}
        self.product_variants: dict[int, ProductVariant] = {}
        self.next_return_id = 1
        self.next_item_id = 1
        self.next_attachment_id = 1
        self.next_refund_id = 1

    async def get_order_for_user(
        self,
        *,
        order_id: int,
        user_id: int,
        for_update: bool = False,
    ) -> Order | None:
        del for_update
        order = self.orders.get(order_id)
        if order is None or order.user_id != user_id:
            return None
        for item in order.items:
            if item.product_variant is not None:
                self.product_variants[item.product_variant.id] = item.product_variant
        return order

    async def get_return_for_order(self, order_id: int) -> ReturnRequest | None:
        return next(
            (
                return_request
                for return_request in self.return_requests.values()
                if return_request.order_id == order_id
            ),
            None,
        )

    async def get_by_id(
        self,
        return_request_id: int,
        *,
        for_update: bool = False,
    ) -> ReturnRequest | None:
        del for_update
        return_request = self.return_requests.get(return_request_id)
        if return_request is not None:
            self._persist_graph(return_request)
        return return_request

    async def list_all(
        self,
        *,
        limit: int,
        offset: int,
        status: ReturnRequestStatus | None = None,
        order_id: int | None = None,
        user_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[ReturnRequest]:
        del created_from, created_to
        items = list(self.return_requests.values())
        if status is not None:
            items = [item for item in items if item.status == status]
        if order_id is not None:
            items = [item for item in items if item.order_id == order_id]
        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        for item in items:
            self._persist_graph(item)
        return items[offset : offset + limit]

    async def lock_variants_by_ids(self, variant_ids: Iterable[int]) -> dict[int, ProductVariant]:
        return {
            variant_id: self.product_variants[variant_id]
            for variant_id in sorted(set(variant_ids))
            if variant_id in self.product_variants
        }

    def add(
        self,
        instance: ReturnRequest | ReturnRequestItem | ReturnRequestAttachment | ReturnRefund,
    ) -> None:
        if isinstance(instance, ReturnRequest):
            self._persist_graph(instance)
            self.return_requests[instance.id] = instance
        elif isinstance(instance, ReturnRefund):
            self._persist_refund(instance)

    def _persist_graph(self, return_request: ReturnRequest) -> None:
        if getattr(return_request, "id", None) is None:
            return_request.id = self.next_return_id
            self.next_return_id += 1
        if getattr(return_request, "created_at", None) is None:
            return_request.created_at = NOW
        return_request.updated_at = getattr(return_request, "updated_at", None) or NOW
        for item in return_request.items:
            if getattr(item, "id", None) is None:
                item.id = self.next_item_id
                self.next_item_id += 1
            item.return_request_id = return_request.id
            item.restocked_quantity = getattr(item, "restocked_quantity", None) or 0
            item.created_at = getattr(item, "created_at", None) or NOW
        for attachment in return_request.attachments:
            if getattr(attachment, "id", None) is None:
                attachment.id = self.next_attachment_id
                self.next_attachment_id += 1
            attachment.return_request_id = return_request.id
            attachment.created_at = getattr(attachment, "created_at", None) or NOW
        if return_request.refund is not None:
            return_request.refund.return_request_id = return_request.id
            self._persist_refund(return_request.refund)

    def _persist_refund(self, refund: ReturnRefund) -> None:
        if getattr(refund, "id", None) is None:
            refund.id = self.next_refund_id
            self.next_refund_id += 1
        refund.created_at = getattr(refund, "created_at", None) or NOW
        refund.updated_at = getattr(refund, "updated_at", None) or NOW


@pytest.mark.asyncio
async def test_non_owner_cannot_access_return_eligibility() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(user_id=2)

    with pytest.raises(AppError, match="Order not found"):
        await service.get_return_eligibility(order_id=1, user_id=1)


@pytest.mark.asyncio
async def test_non_delivered_order_is_not_eligible() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(status_value=OrderStatus.SHIPPED)

    eligibility = await service.get_return_eligibility(order_id=1, user_id=1)

    assert eligibility.eligible is False
    assert eligibility.reason_code == "order_not_delivered"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "elapsed",
    [
        timedelta(0),
        timedelta(hours=23, minutes=59, seconds=59),
        timedelta(hours=24),
    ],
)
async def test_delivered_order_is_eligible_through_exact_24_hour_deadline(
    elapsed: timedelta,
) -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(delivered_at=NOW - elapsed)

    eligibility = await service.get_return_eligibility(order_id=1, user_id=1)

    assert eligibility.eligible is True
    assert eligibility.return_window_until == NOW - elapsed + timedelta(hours=24)
    assert eligibility.items[0].eligible is True
    assert eligibility.items[0].image_url == "/uploads/products/thumb.webp"


@pytest.mark.asyncio
async def test_delivered_order_one_microsecond_after_deadline_is_not_eligible() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(delivered_at=NOW - timedelta(hours=24, microseconds=1))

    eligibility = await service.get_return_eligibility(order_id=1, user_id=1)

    assert eligibility.eligible is False
    assert eligibility.reason_code == "return_window_expired"


@pytest.mark.asyncio
async def test_return_window_uses_delivered_at_instead_of_created_at() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(
        created_at=NOW - timedelta(days=30),
        delivered_at=NOW - timedelta(hours=23),
    )

    eligibility = await service.get_return_eligibility(order_id=1, user_id=1)

    assert eligibility.eligible is True
    assert eligibility.return_window_until == NOW + timedelta(hours=1)


@pytest.mark.asyncio
async def test_delivered_order_without_delivered_at_is_not_eligible() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(created_at=NOW - timedelta(days=3), delivered_at=None)

    eligibility = await service.get_return_eligibility(order_id=1, user_id=1)

    assert eligibility.eligible is False
    assert eligibility.reason_code == "delivered_at_missing"
    assert eligibility.return_window_until is None


@pytest.mark.asyncio
async def test_order_with_only_non_returnable_items_is_not_eligible() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(items=[_order_item(item_id=1, is_returnable=False)])

    eligibility = await service.get_return_eligibility(order_id=1, user_id=1)

    assert eligibility.eligible is False
    assert eligibility.reason_code == "no_returnable_items"
    assert eligibility.items[0].ineligible_reason == "non_returnable"


@pytest.mark.asyncio
async def test_order_with_mixed_items_reports_per_item_eligibility() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(
        items=[
            _order_item(item_id=1, product_name="Returnable", is_returnable=True),
            _order_item(item_id=2, product_name="Final sale", is_returnable=False),
        ],
    )

    eligibility = await service.get_return_eligibility(order_id=1, user_id=1)

    assert eligibility.eligible is True
    assert [item.eligible for item in eligibility.items] == [True, False]
    assert eligibility.items[1].ineligible_reason == "non_returnable"


@pytest.mark.asyncio
async def test_existing_return_request_makes_order_not_eligible() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()
    repository.add(_return_request(order_id=1, user_id=1))

    eligibility = await service.get_return_eligibility(order_id=1, user_id=1)

    assert eligibility.eligible is False
    assert eligibility.reason_code == "return_request_exists"
    assert eligibility.return_request_id == 1


@pytest.mark.asyncio
async def test_customer_creates_return_request_for_one_item() -> None:
    service, repository, session, _storage = _returns_service()
    repository.orders[1] = _order()

    created = await service.create_return_request(
        order_id=1,
        user_id=1,
        payload=_payload([(1, 1)]),
        files=[_upload_file("proof.jpg", b"image", "image/jpeg")],
    )

    assert created.status == ReturnRequestStatus.PENDING
    assert created.return_number.startswith("RET-")
    assert created.message == "Заявка отправлена. Продавец свяжется с вами."
    assert created.items[0].order_item_id == 1
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_return_creation_triggers_seller_notification_after_commit() -> None:
    notifier = FakeReturnNotifier()
    service, repository, session, _storage = _returns_service(seller_notifier=notifier)
    notifier.session = session
    repository.orders[1] = _order()

    created = await service.create_return_request(
        order_id=1,
        user_id=1,
        payload=_payload([(1, 1)]),
        files=[_upload_file("proof.jpg", b"image", "image/jpeg")],
    )

    assert notifier.requests[0].id == created.id
    assert notifier.commit_counts == [1]


@pytest.mark.asyncio
async def test_return_notification_failure_does_not_fail_request() -> None:
    notifier = FakeReturnNotifier(fail=True)
    service, repository, session, _storage = _returns_service(seller_notifier=notifier)
    repository.orders[1] = _order()

    created = await service.create_return_request(
        order_id=1,
        user_id=1,
        payload=_payload([(1, 1)]),
        files=[_upload_file("proof.jpg", b"image", "image/jpeg")],
    )

    assert created.status == ReturnRequestStatus.PENDING
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_return_notification_uses_returns_chat_with_seller_fallback(monkeypatch) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7

    monkeypatch.setattr(settings, "telegram_returns_chat_id", None)
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "seller-chat")
    fallback_telegram = FakeTelegramService()
    fallback_notifier = TelegramReturnSellerNotifier(telegram_service=fallback_telegram)

    await fallback_notifier.notify_return_request_created(return_request)

    assert fallback_telegram.sent_messages[0][0] == "seller-chat"
    assert "Новая заявка на возврат" in fallback_telegram.sent_messages[0][1]

    monkeypatch.setattr(settings, "telegram_orders_chat_id", "orders-chat")
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "returns-chat")
    returns_telegram = FakeTelegramService()
    returns_notifier = TelegramReturnSellerNotifier(telegram_service=returns_telegram)

    await returns_notifier.notify_return_request_created(return_request)

    assert returns_telegram.sent_messages[0][0] == "returns-chat"


@pytest.mark.asyncio
async def test_return_notification_does_not_fall_back_to_orders_chat(monkeypatch) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7

    monkeypatch.setattr(settings, "telegram_orders_chat_id", "orders-chat")
    monkeypatch.setattr(settings, "telegram_returns_chat_id", None)
    monkeypatch.setattr(settings, "telegram_seller_chat_id", None)
    telegram = FakeTelegramService()
    notifier = TelegramReturnSellerNotifier(telegram_service=telegram)

    await notifier.notify_return_request_created(return_request)

    assert telegram.sent_messages == []


@pytest.mark.asyncio
async def test_return_notification_without_attachments_sends_text_with_inline_buttons(
    monkeypatch,
) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "returns-chat")
    telegram = FakeTelegramService()
    notifier = TelegramReturnSellerNotifier(telegram_service=telegram)

    await notifier.notify_return_request_created(return_request)

    assert len(telegram.sent_messages) == 1
    assert telegram.photos == []
    assert telegram.videos == []
    _chat_id, message, reply_markup = telegram.sent_messages[0]
    assert "Новая заявка на возврат" in message
    assert "Статус: Ожидает решения" in message
    assert reply_markup == {
        "inline_keyboard": [
            [
                {"text": "Подтвердить", "callback_data": "return:approve:7"},
                {"text": "Отклонить", "callback_data": "return:reject:7"},
            ]
        ]
    }


@pytest.mark.asyncio
async def test_return_notification_sends_image_attachment_upload(monkeypatch) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7
    return_request.attachments.append(
        _return_attachment(
            file_path="returns/proof.jpg",
            original_filename="proof.jpg",
            mime_type="image/jpeg",
            media_type="image",
        )
    )
    storage = FakeStorage()
    storage.saved["returns/proof.jpg"] = b"image-bytes"
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "returns-chat")
    telegram = FakeTelegramService()
    notifier = TelegramReturnSellerNotifier(telegram_service=telegram, storage=storage)

    await notifier.notify_return_request_created(return_request)

    assert telegram.photos == [
        (
            "returns-chat",
            b"image-bytes",
            "proof.jpg",
            "image/jpeg",
            "Вложение к возврату #RET-00000001",
            101,
        )
    ]


@pytest.mark.asyncio
async def test_return_notification_sends_video_attachment_upload(monkeypatch) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7
    return_request.attachments.append(
        _return_attachment(
            file_path="returns/proof.mp4",
            original_filename="proof.mp4",
            mime_type="video/mp4",
            media_type="video",
        )
    )
    storage = FakeStorage()
    storage.saved["returns/proof.mp4"] = b"video-bytes"
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "returns-chat")
    telegram = FakeTelegramService()
    notifier = TelegramReturnSellerNotifier(telegram_service=telegram, storage=storage)

    await notifier.notify_return_request_created(return_request)

    assert telegram.videos == [
        (
            "returns-chat",
            b"video-bytes",
            "proof.mp4",
            "video/mp4",
            "Вложение к возврату #RET-00000001",
            101,
        )
    ]


@pytest.mark.asyncio
async def test_missing_return_media_file_is_logged_and_does_not_fail(
    monkeypatch,
    caplog,
) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7
    return_request.attachments.append(
        _return_attachment(
            file_path="returns/missing.jpg",
            original_filename="missing.jpg",
            mime_type="image/jpeg",
            media_type="image",
        )
    )
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "returns-chat")
    telegram = FakeTelegramService()
    notifier = TelegramReturnSellerNotifier(
        telegram_service=telegram,
        storage=FakeStorage(),
    )

    with caplog.at_level("WARNING"):
        await notifier.notify_return_request_created(return_request)

    assert len(telegram.sent_messages) == 1
    assert telegram.photos == []
    assert "returns.seller_notification_attachment_read_failed" in caplog.messages


@pytest.mark.asyncio
async def test_return_media_send_failure_is_logged_and_remaining_media_continues(
    monkeypatch,
    caplog,
) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7
    return_request.attachments.extend(
        [
            _return_attachment(
                file_path="returns/proof.jpg",
                original_filename="proof.jpg",
                mime_type="image/jpeg",
                media_type="image",
                position=0,
            ),
            _return_attachment(
                attachment_id=2,
                file_path="returns/proof.mp4",
                original_filename="proof.mp4",
                mime_type="video/mp4",
                media_type="video",
                position=1,
            ),
        ]
    )
    storage = FakeStorage()
    storage.saved["returns/proof.jpg"] = b"image-bytes"
    storage.saved["returns/proof.mp4"] = b"video-bytes"
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "returns-chat")
    telegram = FakeTelegramService(fail_photo=True)
    notifier = TelegramReturnSellerNotifier(telegram_service=telegram, storage=storage)

    with caplog.at_level("WARNING"):
        await notifier.notify_return_request_created(return_request)

    assert telegram.videos == [
        (
            "returns-chat",
            b"video-bytes",
            "proof.mp4",
            "video/mp4",
            "Вложение к возврату #RET-00000001",
            101,
        )
    ]
    assert "returns.seller_notification_attachment_delivery_failed" in caplog.messages


@pytest.mark.asyncio
async def test_return_text_send_failure_does_not_fail_media_upload(monkeypatch) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7
    return_request.attachments.append(
        _return_attachment(
            file_path="returns/proof.jpg",
            original_filename="proof.jpg",
            mime_type="image/jpeg",
            media_type="image",
        )
    )
    storage = FakeStorage()
    storage.saved["returns/proof.jpg"] = b"image-bytes"
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "returns-chat")
    telegram = FakeTelegramService(fail_message=True)
    notifier = TelegramReturnSellerNotifier(telegram_service=telegram, storage=storage)

    await notifier.notify_return_request_created(return_request)

    assert telegram.sent_messages == []
    assert telegram.photos == [
        (
            "returns-chat",
            b"image-bytes",
            "proof.jpg",
            "image/jpeg",
            "Вложение к возврату #RET-00000001",
            None,
        )
    ]


@pytest.mark.asyncio
async def test_return_notification_text_does_not_expose_raw_attachment_path(
    monkeypatch,
) -> None:
    return_request = _return_request(order_id=1, user_id=1)
    return_request.id = 7
    return_request.attachments.append(
        _return_attachment(
            file_path="returns/proof.jpg",
            original_filename="proof.jpg",
            mime_type="image/jpeg",
            media_type="image",
        )
    )
    storage = FakeStorage()
    storage.saved["returns/proof.jpg"] = b"image-bytes"
    monkeypatch.setattr(settings, "telegram_returns_chat_id", "returns-chat")
    telegram = FakeTelegramService()
    notifier = TelegramReturnSellerNotifier(telegram_service=telegram, storage=storage)

    await notifier.notify_return_request_created(return_request)

    message = telegram.sent_messages[0][1]
    assert "returns/proof.jpg" not in message
    assert "proof.jpg" not in message


@pytest.mark.asyncio
async def test_customer_creates_return_request_with_multiple_items() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(
        items=[
            _order_item(item_id=1, quantity=2),
            _order_item(item_id=2, product_id=2, variant_id=2, sku="SKU-2"),
        ],
    )

    created = await service.create_return_request(
        order_id=1,
        user_id=1,
        payload=_payload([(1, 2), (2, 1)]),
        files=[_upload_file("proof.jpg", b"image", "image/jpeg")],
    )

    assert [item.order_item_id for item in created.items] == [1, 2]
    assert [item.quantity for item in created.items] == [2, 1]


@pytest.mark.asyncio
async def test_return_request_must_have_at_least_one_item() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()

    with pytest.raises(AppError, match="At least one item"):
        await service.create_return_request(order_id=1, user_id=1, payload=_payload([]))


@pytest.mark.asyncio
async def test_cannot_return_item_from_another_order() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()

    with pytest.raises(AppError, match="does not belong"):
        await service.create_return_request(order_id=1, user_id=1, payload=_payload([(99, 1)]))


@pytest.mark.asyncio
async def test_cannot_return_non_returnable_order_item() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(items=[_order_item(item_id=1, is_returnable=False)])

    with pytest.raises(AppError, match="no returnable items"):
        await service.create_return_request(order_id=1, user_id=1, payload=_payload([(1, 1)]))


@pytest.mark.asyncio
async def test_cannot_return_quantity_above_purchased_quantity() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(items=[_order_item(item_id=1, quantity=1)])

    with pytest.raises(AppError, match="exceeds purchased quantity"):
        await service.create_return_request(order_id=1, user_id=1, payload=_payload([(1, 2)]))


@pytest.mark.asyncio
async def test_cannot_create_return_for_non_delivered_order() -> None:
    notifier = FakeReturnNotifier()
    service, repository, _session, _storage = _returns_service(seller_notifier=notifier)
    repository.orders[1] = _order(status_value=OrderStatus.PROCESSING)

    with pytest.raises(AppError, match="only after delivery"):
        await service.create_return_request(order_id=1, user_id=1, payload=_payload([(1, 1)]))
    assert notifier.requests == []


@pytest.mark.asyncio
async def test_cannot_create_return_after_window() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(delivered_at=NOW - timedelta(hours=24, microseconds=1))

    with pytest.raises(AppError, match="Срок оформления возврата истёк") as exc_info:
        await service.create_return_request(order_id=1, user_id=1, payload=_payload([(1, 1)]))
    assert exc_info.value.status_code == 400


def test_direct_return_api_request_cannot_bypass_expired_deadline() -> None:
    app = create_app()
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order(
        delivered_at=NOW - timedelta(hours=24, microseconds=1)
    )

    app.dependency_overrides[get_current_user] = lambda: _user(role=UserRole.USER)
    app.dependency_overrides[get_returns_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/orders/1/returns",
                json=_payload([(1, 1)]).model_dump(mode="json"),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {
        "detail": (
            "Срок оформления возврата истёк. Возврат доступен в течение 24 часов "
            "после получения заказа."
        )
    }


@pytest.mark.asyncio
async def test_cannot_create_second_return_request_for_same_order() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()
    repository.add(_return_request(order_id=1, user_id=1))

    with pytest.raises(AppError, match="already exists"):
        await service.create_return_request(order_id=1, user_id=1, payload=_payload([(1, 1)]))


@pytest.mark.asyncio
async def test_created_return_item_snapshots_order_item_data() -> None:
    service, repository, _session, _storage = _returns_service()
    order_item = _order_item(
        item_id=1,
        product_name="Original hoodie",
        brand="ICON",
        sku="OLD-SKU",
        size="M",
        color="Black",
        unit_price=Decimal("99.90"),
        quantity=2,
    )
    repository.orders[1] = _order(items=[order_item])

    created = await service.create_return_request(
        order_id=1,
        user_id=1,
        payload=_payload([(1, 1)]),
        files=[_upload_file("proof.jpg", b"image", "image/jpeg")],
    )
    order_item.product.name = "Changed product"
    order_item.product.brand = "Changed brand"

    item = created.items[0]
    assert item.product_name == "Original hoodie"
    assert item.product_brand == "ICON"
    assert item.sku == "OLD-SKU"
    assert item.size == "M"
    assert item.color == "Black"
    assert item.unit_price == Decimal("99.90")


@pytest.mark.asyncio
async def test_rejects_return_request_without_attachments_before_persistence() -> None:
    service, repository, session, storage = _returns_service()
    repository.orders[1] = _order()

    with pytest.raises(AppError, match="At least one return attachment is required") as exc_info:
        await service.create_return_request(
            order_id=1,
            user_id=1,
            payload=_payload([(1, 1)]),
            files=[],
        )

    assert exc_info.value.status_code == 400
    assert repository.return_requests == {}
    assert repository.next_attachment_id == 1
    assert session.commit_count == 0
    assert storage.saved == {}


@pytest.mark.asyncio
async def test_accepts_valid_image_attachment_and_stores_metadata() -> None:
    service, repository, _session, storage = _returns_service()
    repository.orders[1] = _order()

    created = await service.create_return_request(
        order_id=1,
        user_id=1,
        payload=_payload([(1, 1)]),
        files=[_upload_file("proof.jpg", b"image-bytes", "image/jpeg")],
    )

    assert created.attachments[0].file_path == "returns/return-1.jpg"
    assert created.attachments[0].original_filename == "proof.jpg"
    assert created.attachments[0].mime_type == "image/jpeg"
    assert created.attachments[0].media_type == "image"
    assert storage.saved["returns/return-1.jpg"] == b"image-bytes"


@pytest.mark.asyncio
async def test_accepts_valid_video_attachment() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()

    created = await service.create_return_request(
        order_id=1,
        user_id=1,
        payload=_payload([(1, 1)]),
        files=[_upload_file("proof.mp4", b"video-bytes", "video/mp4")],
    )

    assert created.attachments[0].media_type == "video"
    assert created.attachments[0].file_path.endswith(".mp4")


@pytest.mark.asyncio
async def test_rejects_unsupported_attachment_mime_type() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()

    with pytest.raises(AppError, match="Invalid MIME type"):
        await service.create_return_request(
            order_id=1,
            user_id=1,
            payload=_payload([(1, 1)]),
            files=[_upload_file("proof.txt", b"text", "text/plain")],
        )


@pytest.mark.asyncio
async def test_rejects_more_than_five_attachments() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()
    files = [_upload_file(f"proof-{index}.jpg", b"x", "image/jpeg") for index in range(6)]

    with pytest.raises(AppError, match="Too many"):
        await service.create_return_request(
            order_id=1,
            user_id=1,
            payload=_payload([(1, 1)]),
            files=files,
        )


@pytest.mark.asyncio
async def test_accepts_five_return_attachments() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()
    files = [_upload_file(f"proof-{index}.jpg", b"x", "image/jpeg") for index in range(5)]

    created = await service.create_return_request(
        order_id=1,
        user_id=1,
        payload=_payload([(1, 1)]),
        files=files,
    )

    assert len(created.attachments) == 5


@pytest.mark.asyncio
async def test_rejects_attachment_over_twenty_mb() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.orders[1] = _order()

    with pytest.raises(AppError, match="File size exceeds limit"):
        await service.create_return_request(
            order_id=1,
            user_id=1,
            payload=_payload([(1, 1)]),
            files=[
                _upload_file(
                    "proof.jpg",
                    b"x" * (MAX_RETURN_ATTACHMENT_SIZE_BYTES + 1),
                    "image/jpeg",
                )
            ],
        )


@pytest.mark.asyncio
async def test_file_save_failure_rolls_back_without_partial_return_request() -> None:
    service, repository, session, storage = _returns_service(storage=FakeStorage(fail_save=True))
    repository.orders[1] = _order()

    with pytest.raises(AppError, match="Return request create failed"):
        await service.create_return_request(
            order_id=1,
            user_id=1,
            payload=_payload([(1, 1)]),
            files=[_upload_file("proof.jpg", b"image", "image/jpeg")],
        )

    assert session.rollback_count == 1
    assert storage.saved == {}


@pytest.mark.asyncio
async def test_seller_admin_can_list_and_read_return_requests() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1))

    listed = await service.list_admin_return_requests(limit=20, offset=0)
    detail = await service.get_admin_return_request(1)

    assert listed.items[0].id == 1
    assert detail.order_id == 1


def test_return_request_status_enum_includes_lifecycle_statuses() -> None:
    assert ReturnRequestStatus.COMPLETED.value == "COMPLETED"
    assert ReturnRequestStatus.CANCELLED.value == "CANCELLED"


@pytest.mark.asyncio
async def test_seller_admin_can_approve_pending_return_request() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1))

    approved = await service.approve(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnDecisionRequest(decision_comment="Approved"),
    )

    assert approved.status == ReturnRequestStatus.APPROVED
    assert approved.decided_by_user_id == 10
    assert approved.decided_at == NOW
    assert approved.decision_comment == "Approved"


@pytest.mark.asyncio
async def test_seller_admin_can_reject_pending_return_request() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1))

    rejected = await service.reject(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnDecisionRequest(decision_comment="Rejected"),
    )

    assert rejected.status == ReturnRequestStatus.REJECTED
    assert rejected.decision_comment == "Rejected"


@pytest.mark.asyncio
async def test_cannot_decide_already_decided_return_request() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    with pytest.raises(AppError, match="already decided"):
        await service.approve(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnDecisionRequest(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_status",
    [
        ReturnRequestStatus.APPROVED,
        ReturnRequestStatus.REJECTED,
        ReturnRequestStatus.COMPLETED,
        ReturnRequestStatus.CANCELLED,
    ],
)
async def test_approve_reject_still_only_work_from_pending(
    terminal_status: ReturnRequestStatus,
) -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1, status_value=terminal_status))

    with pytest.raises(AppError, match="already decided"):
        await service.approve(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnDecisionRequest(),
        )
    with pytest.raises(AppError, match="already decided"):
        await service.reject(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnDecisionRequest(),
        )


@pytest.mark.asyncio
async def test_customer_can_cancel_own_pending_return_request() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1))

    cancelled = await service.cancel_customer(
        return_request_id=1,
        user_id=1,
        payload=ReturnLifecycleCommentRequest(comment="Changed mind"),
    )

    assert cancelled.status == ReturnRequestStatus.CANCELLED
    assert cancelled.cancelled_at == NOW
    assert cancelled.cancelled_by_user_id == 1
    assert cancelled.cancellation_comment == "Changed mind"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_value",
    [
        ReturnRequestStatus.APPROVED,
        ReturnRequestStatus.REJECTED,
        ReturnRequestStatus.COMPLETED,
        ReturnRequestStatus.CANCELLED,
    ],
)
async def test_customer_cannot_cancel_non_pending_return_request(
    status_value: ReturnRequestStatus,
) -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1, status_value=status_value))

    with pytest.raises(AppError, match="pending"):
        await service.cancel_customer(
            return_request_id=1,
            user_id=1,
            payload=ReturnLifecycleCommentRequest(),
        )


@pytest.mark.asyncio
async def test_customer_cannot_cancel_another_users_return_request() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=2))

    with pytest.raises(AppError, match="not found"):
        await service.cancel_customer(
            return_request_id=1,
            user_id=1,
            payload=ReturnLifecycleCommentRequest(),
        )


@pytest.mark.asyncio
async def test_seller_admin_can_complete_approved_return_request() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    completed = await service.complete(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnLifecycleCommentRequest(comment="Done manually"),
    )

    assert completed.status == ReturnRequestStatus.COMPLETED
    assert completed.completed_at == NOW
    assert completed.completed_by_user_id == 10
    assert completed.completion_comment == "Done manually"
    assert completed.cancelled_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_value",
    [
        ReturnRequestStatus.PENDING,
        ReturnRequestStatus.REJECTED,
        ReturnRequestStatus.COMPLETED,
        ReturnRequestStatus.CANCELLED,
    ],
)
async def test_seller_admin_cannot_complete_non_approved_return_request(
    status_value: ReturnRequestStatus,
) -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1, status_value=status_value))

    with pytest.raises(AppError, match="after approval"):
        await service.complete(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnLifecycleCommentRequest(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_value",
    [
        ReturnRequestStatus.PENDING,
        ReturnRequestStatus.REJECTED,
        ReturnRequestStatus.COMPLETED,
        ReturnRequestStatus.CANCELLED,
    ],
)
async def test_cannot_process_non_approved_return_request(
    status_value: ReturnRequestStatus,
) -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1, status_value=status_value))

    with pytest.raises(AppError, match="after approval"):
        await service.process(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnProcessRequest(),
        )


@pytest.mark.asyncio
async def test_process_approved_return_records_default_refund_without_completion() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    processed = await service.process(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnProcessRequest(complete=False),
    )

    assert processed.status == ReturnRequestStatus.APPROVED
    assert processed.refund is not None
    assert processed.refund.amount == Decimal("59.90")
    assert processed.refund.currency == "RUB"
    assert processed.refund.status == ReturnRefundStatus.RECORDED
    assert processed.refund.processed_at == NOW
    assert processed.refund.processed_by_user_id == 10
    assert processed.total_return_amount == Decimal("59.90")
    assert processed.can_process is True
    assert processed.can_complete is True


@pytest.mark.asyncio
async def test_process_rejects_refund_amount_above_return_total() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    with pytest.raises(AppError, match="exceeds returned items total"):
        await service.process(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnProcessRequest(
                refund={"amount": Decimal("60.00"), "currency": "RUB"},
            ),
        )


@pytest.mark.asyncio
async def test_process_restocks_variant_and_completes_return_request() -> None:
    service, repository, _session, _storage = _returns_service()
    variant = _variant(stock_quantity=3)
    repository.product_variants[1] = variant
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    processed = await service.process(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnProcessRequest(
            refund={
                "amount": Decimal("49.90"),
                "currency": "RUB",
                "method": "manual_cash",
                "comment": "Cash refund",
            },
            restock_items=[{"return_request_item_id": 1, "quantity": 1}],
            complete=True,
            comment="Return processed",
        ),
    )

    assert variant.stock_quantity == 4
    assert processed.status == ReturnRequestStatus.COMPLETED
    assert processed.completed_at == NOW
    assert processed.completed_by_user_id == 10
    assert processed.completion_comment == "Return processed"
    assert processed.refund is not None
    assert processed.refund.amount == Decimal("49.90")
    assert processed.refund.method == "manual_cash"
    assert processed.refund.comment == "Cash refund"
    assert processed.items[0].restocked_quantity == 1
    assert processed.items[0].restocked_at == NOW
    assert processed.items[0].restocked_by_user_id == 10
    assert processed.items[0].remaining_restockable_quantity == 0
    assert processed.items[0].can_restock is False
    assert processed.can_process is False
    assert processed.can_complete is False


@pytest.mark.asyncio
async def test_process_restock_is_transactional_when_variant_is_missing() -> None:
    service, repository, session, _storage = _returns_service()
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    with pytest.raises(AppError, match="Product variant not found"):
        await service.process(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnProcessRequest(
                refund={"amount": Decimal("10.00"), "currency": "RUB"},
                restock_items=[{"return_request_item_id": 1, "quantity": 1}],
            ),
        )

    stored = repository.return_requests[1]
    assert stored.status == ReturnRequestStatus.APPROVED
    assert stored.refund is None
    assert stored.items[0].restocked_quantity == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_process_cannot_restock_more_than_returned_quantity() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.product_variants[1] = _variant(stock_quantity=3)
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    with pytest.raises(AppError, match="exceeds returned quantity"):
        await service.process(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnProcessRequest(
                restock_items=[{"return_request_item_id": 1, "quantity": 2}],
            ),
        )


@pytest.mark.asyncio
async def test_process_does_not_double_restock_same_quantity() -> None:
    service, repository, _session, _storage = _returns_service()
    variant = _variant(stock_quantity=3)
    repository.product_variants[1] = variant
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    await service.process(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnProcessRequest(
            restock_items=[{"return_request_item_id": 1, "quantity": 1}],
            complete=False,
        ),
    )
    await service.process(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnProcessRequest(
            restock_items=[{"return_request_item_id": 1, "quantity": 1}],
            complete=False,
        ),
    )

    assert variant.stock_quantity == 4
    assert repository.return_requests[1].items[0].restocked_quantity == 1


@pytest.mark.asyncio
async def test_process_partial_restock_uses_only_additional_delta() -> None:
    service, repository, _session, _storage = _returns_service()
    variant = _variant(stock_quantity=3)
    return_request = _return_request(
        order_id=1,
        user_id=1,
        status_value=ReturnRequestStatus.APPROVED,
    )
    return_request.items[0].quantity = 3
    repository.product_variants[1] = variant
    repository.add(return_request)

    await service.process(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnProcessRequest(
            restock_items=[{"return_request_item_id": 1, "quantity": 1}],
            complete=False,
        ),
    )
    await service.process(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnProcessRequest(
            restock_items=[{"return_request_item_id": 1, "quantity": 3}],
            complete=False,
        ),
    )

    assert variant.stock_quantity == 6
    assert repository.return_requests[1].items[0].restocked_quantity == 3


@pytest.mark.asyncio
async def test_process_cannot_restock_item_without_variant() -> None:
    service, repository, _session, _storage = _returns_service()
    return_request = _return_request(
        order_id=1,
        user_id=1,
        status_value=ReturnRequestStatus.APPROVED,
    )
    return_request.items[0].product_variant_id = None
    repository.add(return_request)

    detail = await service.get_admin_return_request(1)
    assert detail.items[0].remaining_restockable_quantity == 0
    assert detail.items[0].can_restock is False

    with pytest.raises(AppError, match="no product variant"):
        await service.process(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnProcessRequest(
                restock_items=[{"return_request_item_id": 1, "quantity": 1}],
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_value",
    [ReturnRequestStatus.PENDING, ReturnRequestStatus.APPROVED],
)
async def test_seller_admin_can_cancel_pending_or_approved_return_request(
    status_value: ReturnRequestStatus,
) -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1, status_value=status_value))

    cancelled = await service.cancel_admin(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnLifecycleCommentRequest(comment="Operational cancel"),
    )

    assert cancelled.status == ReturnRequestStatus.CANCELLED
    assert cancelled.cancelled_at == NOW
    assert cancelled.cancelled_by_user_id == 10
    assert cancelled.cancellation_comment == "Operational cancel"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_value",
    [
        ReturnRequestStatus.REJECTED,
        ReturnRequestStatus.COMPLETED,
        ReturnRequestStatus.CANCELLED,
    ],
)
async def test_seller_admin_cannot_cancel_final_return_request(
    status_value: ReturnRequestStatus,
) -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1, status_value=status_value))

    with pytest.raises(AppError, match="pending or approved"):
        await service.cancel_admin(
            return_request_id=1,
            actor_user_id=10,
            payload=ReturnLifecycleCommentRequest(),
        )


@pytest.mark.asyncio
async def test_seller_panel_list_sees_return_decision_status() -> None:
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1))

    await service.approve(
        return_request_id=1,
        actor_user_id=10,
        payload=ReturnDecisionRequest(decision_comment="Approved"),
    )
    listed = await service.list_admin_return_requests(limit=20, offset=0)

    assert listed.items[0].status == ReturnRequestStatus.APPROVED
    assert listed.items[0].decided_by_user_id == 10


def test_admin_approve_reject_routes_still_use_shared_return_service() -> None:
    app = create_app()
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1))
    repository.add(_return_request(order_id=2, user_id=1))

    async def current_user() -> User:
        return _user(role=UserRole.SELLER, user_id=10)

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_returns_service] = lambda: service
    try:
        client = TestClient(app)
        approve_response = client.post(
            "/api/v1/returns/admin/1/approve",
            json={"decision_comment": "Approved through route"},
        )
        reject_response = client.post(
            "/api/v1/returns/admin/2/reject",
            json={"decision_comment": "Rejected through route"},
        )
    finally:
        app.dependency_overrides.clear()

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "APPROVED"
    assert approve_response.json()["decided_by_user_id"] == 10
    assert approve_response.json()["decision_comment"] == "Approved through route"
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "REJECTED"
    assert reject_response.json()["decision_comment"] == "Rejected through route"


def test_customer_cancel_route_uses_authenticated_owner() -> None:
    app = create_app()
    service, repository, _session, _storage = _returns_service()
    repository.add(_return_request(order_id=1, user_id=1))

    async def current_user() -> User:
        return _user(role=UserRole.USER, user_id=1)

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_returns_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/returns/1/cancel",
            json={"comment": "No longer needed"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert response.json()["cancelled_by_user_id"] == 1
    assert response.json()["cancellation_comment"] == "No longer needed"


def test_admin_complete_cancel_routes_return_lifecycle_fields() -> None:
    app = create_app()
    service, repository, _session, _storage = _returns_service()
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )
    repository.add(_return_request(order_id=2, user_id=1))

    async def current_user() -> User:
        return _user(role=UserRole.SELLER, user_id=10)

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_returns_service] = lambda: service
    try:
        client = TestClient(app)
        complete_response = client.post(
            "/api/v1/returns/admin/1/complete",
            json={"comment": "Completed by hand"},
        )
        cancel_response = client.post(
            "/api/v1/returns/admin/2/cancel",
            json={"comment": "Cancelled by seller"},
        )
    finally:
        app.dependency_overrides.clear()

    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "COMPLETED"
    assert complete_response.json()["completed_by_user_id"] == 10
    assert complete_response.json()["completion_comment"] == "Completed by hand"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"
    assert cancel_response.json()["cancelled_by_user_id"] == 10
    assert cancel_response.json()["cancellation_comment"] == "Cancelled by seller"


def test_admin_process_route_records_refund_restock_and_completion() -> None:
    app = create_app()
    service, repository, _session, _storage = _returns_service()
    repository.product_variants[1] = _variant(stock_quantity=2)
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    async def current_user() -> User:
        return _user(role=UserRole.SELLER, user_id=10)

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_returns_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/returns/admin/1/process",
            json={
                "refund": {
                    "amount": "59.90",
                    "currency": "rub",
                    "method": "manual_transfer",
                    "comment": "Manual transfer",
                },
                "restock_items": [{"return_request_item_id": 1, "quantity": 1}],
                "complete": True,
                "comment": "Processed through route",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["completed_by_user_id"] == 10
    assert payload["completion_comment"] == "Processed through route"
    assert payload["refund"]["amount"] == "59.90"
    assert payload["refund"]["currency"] == "RUB"
    assert payload["refund"]["method"] == "manual_transfer"
    assert payload["items"][0]["restocked_quantity"] == 1
    assert payload["items"][0]["remaining_restockable_quantity"] == 0
    assert repository.product_variants[1].stock_quantity == 3


def test_admin_process_route_rejects_negative_refund_amount() -> None:
    app = create_app()
    service, repository, _session, _storage = _returns_service()
    repository.add(
        _return_request(order_id=1, user_id=1, status_value=ReturnRequestStatus.APPROVED)
    )

    async def current_user() -> User:
        return _user(role=UserRole.ADMIN, user_id=10)

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_returns_service] = lambda: service
    try:
        response = TestClient(app).post(
            "/api/v1/returns/admin/1/process",
            json={"refund": {"amount": "-1.00", "currency": "RUB"}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_regular_user_cannot_access_admin_return_endpoints() -> None:
    app = create_app()

    async def current_user() -> User:
        return _user(role=UserRole.USER)

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_returns_service] = lambda: object()
    try:
        client = TestClient(app)
        response = client.get("/api/v1/returns/admin")
        process_response = client.post(
            "/api/v1/returns/admin/1/process",
            json={"refund": {"amount": "0.00", "currency": "RUB"}},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert process_response.status_code == 403


def _returns_service(
    *,
    storage: FakeStorage | None = None,
    seller_notifier: FakeReturnNotifier | None = None,
) -> tuple[ReturnsService, FakeReturnsRepository, DummySession, FakeStorage]:
    session = DummySession()
    storage = storage or FakeStorage()
    service = ReturnsService(
        session,
        storage=storage,
        seller_notifier=seller_notifier or FakeReturnNotifier(),
        now_factory=lambda: NOW,
        users_service=FakeUserBlocksService(),
    )
    repository = FakeReturnsRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session, storage


def _payload(items: Iterable[tuple[int, int]]) -> ReturnRequestCreate:
    return ReturnRequestCreate(
        reason="Не подошёл размер",
        comment="Комментарий пользователя",
        items=[
            ReturnRequestItemCreate(order_item_id=order_item_id, quantity=quantity)
            for order_item_id, quantity in items
        ],
    )


def _return_request(
    *,
    order_id: int,
    user_id: int,
    status_value: ReturnRequestStatus = ReturnRequestStatus.PENDING,
) -> ReturnRequest:
    return ReturnRequest(
        return_number=f"RET-{order_id:08d}",
        order_id=order_id,
        user_id=user_id,
        status=status_value,
        reason="Reason",
        comment=None,
        items=[
            ReturnRequestItem(
                order_item_id=1,
                product_id=1,
                product_variant_id=1,
                product_name="Hoodie",
                product_brand="ICON",
                sku="SKU-1",
                size="M",
                color="Black",
                unit_price=Decimal("59.90"),
                quantity=1,
            )
        ],
        attachments=[],
        decided_at=None,
        decided_by_user_id=None,
        decision_comment=None,
    )


def _return_attachment(
    *,
    file_path: str,
    original_filename: str,
    mime_type: str,
    media_type: str,
    attachment_id: int = 1,
    position: int = 0,
) -> ReturnRequestAttachment:
    return ReturnRequestAttachment(
        id=attachment_id,
        return_request_id=1,
        file_path=file_path,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=12,
        media_type=media_type,
        position=position,
        created_at=NOW,
    )


def _order(
    *,
    order_id: int = 1,
    user_id: int = 1,
    status_value: OrderStatus = OrderStatus.DELIVERED,
    created_at: datetime = NOW - timedelta(days=2),
    delivered_at: datetime | None = NOW - timedelta(days=1),
    items: list[OrderItem] | None = None,
) -> Order:
    order = Order(
        id=order_id,
        order_number=f"ORD-{order_id:06d}",
        user_id=user_id,
        status=status_value,
        subtotal_amount=Decimal("59.90"),
        discount_amount=Decimal("0.00"),
        promo_code_id=None,
        promo_code_code=None,
        total_amount=Decimal("59.90"),
        delivery_price=Decimal("0.00"),
        contact_name="Ada",
        contact_phone="+79999999999",
        delivery_method=OrderDeliveryMethod.ROUTE_TAXI,
        delivery_address="Main street",
        delivery_comment=None,
        delivered_at=delivered_at,
        items=items or [_order_item(item_id=1)],
        created_at=created_at,
        updated_at=created_at,
    )
    for item in order.items:
        item.order_id = order.id
        item.order = order
    return order


def _order_item(
    *,
    item_id: int,
    product_id: int = 1,
    variant_id: int = 1,
    product_name: str = "Hoodie",
    brand: str = "ICON",
    sku: str = "SKU-1",
    size: str = "M",
    color: str | None = "Black",
    unit_price: Decimal = Decimal("59.90"),
    quantity: int = 1,
    is_returnable: bool = True,
) -> OrderItem:
    product = _product(product_id=product_id, name=product_name, brand=brand)
    variant = _variant(
        variant_id=variant_id,
        product_id=product_id,
        size=size,
        color=color,
        sku=sku,
    )
    return OrderItem(
        id=item_id,
        order_id=1,
        product_id=product_id,
        product_variant_id=variant_id,
        product=product,
        product_variant=variant,
        product_name=product_name,
        variant_size=size,
        variant_size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        variant_color=color,
        variant_sku=sku,
        unit_price=unit_price,
        quantity=quantity,
        subtotal=unit_price * quantity,
        is_returnable=is_returnable,
        created_at=NOW,
    )


def _variant(
    *,
    variant_id: int = 1,
    product_id: int = 1,
    size: str = "M",
    color: str | None = "Black",
    sku: str = "SKU-1",
    stock_quantity: int = 1,
    reserved_quantity: int = 0,
) -> ProductVariant:
    return ProductVariant(
        id=variant_id,
        product_id=product_id,
        size=size,
        color=color,
        sku=sku,
        stock_quantity=stock_quantity,
        reserved_quantity=reserved_quantity,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _product(*, product_id: int, name: str, brand: str) -> Product:
    return Product(
        id=product_id,
        name=name,
        slug=f"product-{product_id}",
        brand=brand,
        description=None,
        base_price=Decimal("59.90"),
        size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        size_group=ProductSizeGroup.CLOTHING,
        status=ProductStatus.ACTIVE,
        is_listed=True,
        is_returnable=True,
        category_id=None,
        images=[
            ProductImage(
                id=product_id,
                product_id=product_id,
                file_path="products/source.webp",
                thumbnail_path="products/thumb.webp",
                card_path="products/card.webp",
                detail_path="products/detail.webp",
                original_filename="source.webp",
                mime_type="image/webp",
                size_bytes=12,
                alt_text=None,
                position=0,
                is_primary=True,
                created_at=NOW,
            )
        ],
        created_at=NOW,
        updated_at=NOW,
    )


def _upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _user(*, role: UserRole, user_id: int = 1) -> User:
    return User(
        id=user_id,
        telegram_id=1001,
        username="user",
        first_name="User",
        last_name=None,
        role=role,
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )
