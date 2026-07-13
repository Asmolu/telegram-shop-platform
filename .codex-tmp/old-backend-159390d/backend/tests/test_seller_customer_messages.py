from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    CustomerServiceNotificationDelivery,
    CustomerServiceNotificationDeliveryStatus,
    CustomerTelegramSubscription,
    User,
    UserRole,
)
from app.main import create_app
from app.modules.customer_notifications.service import (
    CustomerTelegramSender,
    SellerCustomerOrderMessageService,
)
from app.modules.orders.router import get_seller_customer_message_service
from app.modules.telegram.service import TelegramDeliveryError

DEFAULT_SUBSCRIPTION = object()


class DummySession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class FakeRepository:
    def __init__(self, subscription: CustomerTelegramSubscription | None) -> None:
        self.subscription = subscription
        self.deliveries: list[CustomerServiceNotificationDelivery] = []

    async def get_by_user_id(self, user_id: int) -> CustomerTelegramSubscription | None:
        if self.subscription is None or self.subscription.user_id != user_id:
            return None
        return self.subscription

    def add_delivery(self, delivery: CustomerServiceNotificationDelivery) -> None:
        delivery.id = len(self.deliveries) + 1
        delivery.created_at = _now()
        delivery.updated_at = _now()
        self.deliveries.append(delivery)


class FakeOrdersRepository:
    async def get_by_id(self, order_id: int):
        if order_id != 10:
            return None
        return SimpleNamespace(id=10, user_id=1)


class FakeSender:
    def __init__(self, error: TelegramDeliveryError | None = None) -> None:
        self.error = error
        self.messages: list[tuple[int, str]] = []
        self.photos: list[tuple[int, bytes, str, str, str | None]] = []

    async def send_message(self, chat_id: int, message: str) -> int:
        if self.error is not None:
            raise self.error
        self.messages.append((chat_id, message))
        return 501

    async def send_photo(
        self,
        chat_id: int,
        photo: bytes,
        *,
        filename: str,
        mime_type: str,
        caption: str | None = None,
    ) -> int:
        if self.error is not None:
            raise self.error
        self.photos.append((chat_id, photo, filename, mime_type, caption))
        return 502


class FakeUploadsService:
    async def validate_and_read_image(self, _: object):
        return SimpleNamespace(
            content=b"image-bytes",
            original_filename="report.webp",
            mime_type="image/webp",
        )


class FakeAuditService:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record_action(self, **kwargs: object) -> None:
        self.records.append(kwargs)


@pytest.mark.asyncio
async def test_seller_sends_text_to_customer_through_bot_1() -> None:
    service, repository, sender = _service()

    response = await service.send(
        order_id=10,
        actor_user_id=9,
        text="Ваш заказ готов.",
        photo=None,
    )

    assert sender.messages == [(100, "Ваш заказ готов.")]
    assert sender.photos == []
    assert response.telegram_message_id == 501
    assert repository.deliveries[0].status == CustomerServiceNotificationDeliveryStatus.SENT


@pytest.mark.asyncio
async def test_seller_order_message_uses_write_access_user_id_without_private_chat() -> None:
    subscription = _subscription(
        has_chat=False,
        telegram_chat_id=None,
        chat_type="unknown",
        write_access_granted=True,
    )
    service, repository, sender = _service(subscription=subscription)

    response = await service.send(
        order_id=10,
        actor_user_id=9,
        text="Ваш заказ в пути.",
        photo=None,
    )

    assert sender.messages == [(42, "Ваш заказ в пути.")]
    assert response.telegram_message_id == 501
    assert repository.deliveries[0].status == CustomerServiceNotificationDeliveryStatus.SENT
    assert subscription.has_chat is False
    assert subscription.telegram_chat_id is None


@pytest.mark.asyncio
async def test_seller_sends_photo_with_optional_caption_through_bot_1() -> None:
    service, repository, sender = _service()

    response = await service.send(
        order_id=10,
        actor_user_id=9,
        text="Фотоотчёт",
        photo=object(),
    )

    assert sender.messages == []
    assert sender.photos == [(100, b"image-bytes", "report.webp", "image/webp", "Фотоотчёт")]
    assert response.sent_photo is True
    assert repository.deliveries[0].telegram_message_id == 502


@pytest.mark.asyncio
async def test_seller_sends_photo_only_through_bot_1() -> None:
    service, repository, sender = _service()

    response = await service.send(
        order_id=10,
        actor_user_id=9,
        text=None,
        photo=object(),
    )

    assert sender.messages == []
    assert sender.photos == [(100, b"image-bytes", "report.webp", "image/webp", None)]
    assert response.sent_text is False
    assert response.sent_photo is True
    assert repository.deliveries[0].status == CustomerServiceNotificationDeliveryStatus.SENT


def test_customer_sender_uses_bot_1_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_customer_bot_token", "bot-1-token")
    monkeypatch.setattr(settings, "telegram_bot_token", "bot-2-token")

    sender = CustomerTelegramSender()

    assert sender.telegram_service.bot_token == "bot-1-token"
    assert sender.telegram_service.bot_token != settings.telegram_bot_token


@pytest.mark.asyncio
async def test_seller_cannot_send_without_customer_bot_1_chat() -> None:
    service, repository, sender = _service(subscription=None)

    with pytest.raises(AppError, match="не открыл Bot 1"):
        await service.send(
            order_id=10,
            actor_user_id=9,
            text="Сообщение",
            photo=None,
        )

    assert sender.messages == []
    assert repository.deliveries[0].status == CustomerServiceNotificationDeliveryStatus.SKIPPED


@pytest.mark.asyncio
async def test_bot_1_failure_returns_clean_seller_error() -> None:
    service, repository, _ = _service(
        sender_error=TelegramDeliveryError(
            "Forbidden: bot token customer-secret was blocked",
            error_code=403,
            status_code=403,
        )
    )

    with pytest.raises(AppError, match="заблокировал Bot 1") as error:
        await service.send(
            order_id=10,
            actor_user_id=9,
            text="Сообщение",
            photo=None,
        )

    assert "customer-secret" not in error.value.message
    assert repository.deliveries[0].status == CustomerServiceNotificationDeliveryStatus.BLOCKED


def test_regular_user_cannot_send_order_customer_message() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/orders/admin/10/customer-message",
                data={"text": "Сообщение"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_seller_customer_message_route_accepts_photo_only() -> None:
    app = create_app()

    class FakeService:
        async def send(self, **kwargs):
            assert kwargs["text"] is None
            assert kwargs["photo"] is not None
            return {
                "ok": True,
                "order_id": 10,
                "delivery_id": 1,
                "telegram_message_id": 502,
                "sent_text": False,
                "sent_photo": True,
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_seller_customer_message_service] = lambda: FakeService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/orders/admin/10/customer-message",
                files={"photo": ("report.png", b"image", "image/png")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["sent_photo"] is True


def _service(
    *,
    subscription: CustomerTelegramSubscription | None | object = DEFAULT_SUBSCRIPTION,
    sender_error: TelegramDeliveryError | None = None,
):
    if subscription is DEFAULT_SUBSCRIPTION:
        subscription = _subscription()
    session = DummySession()
    repository = FakeRepository(
        subscription if isinstance(subscription, CustomerTelegramSubscription) else None
    )
    sender = FakeSender(sender_error)
    service = SellerCustomerOrderMessageService(
        session,
        repository=repository,
        orders_repository=FakeOrdersRepository(),
        sender=sender,
        uploads_service=FakeUploadsService(),
        audit_service=FakeAuditService(),
        now_factory=_now,
    )
    return service, repository, sender


def _subscription(
    *,
    has_chat: bool = True,
    telegram_chat_id: int | None = 100,
    chat_type: str = "private",
    write_access_granted: bool = False,
) -> CustomerTelegramSubscription:
    return CustomerTelegramSubscription(
        id=7,
        user_id=1,
        telegram_user_id=42,
        telegram_chat_id=telegram_chat_id,
        telegram_username="buyer",
        chat_type=chat_type,
        has_chat=has_chat,
        service_opt_in=True,
        marketing_opt_in=False,
        write_access_granted=write_access_granted,
        write_access_granted_at=_now() if write_access_granted else None,
        created_at=_now(),
        updated_at=_now(),
    )


def _user(role: UserRole) -> User:
    return User(
        id=9,
        telegram_id=900,
        username="seller",
        first_name="Seller",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
