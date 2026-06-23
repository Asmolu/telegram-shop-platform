from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.common.pagination import PageMeta
from app.core.config import settings
from app.db.models import Notification, NotificationChannel, NotificationStatus, User, UserRole
from app.events.names import ORDER_CREATED, ORDER_SHIPPED, ORDER_STATUS_CHANGED, PROMO_USED
from app.main import create_app
from app.modules.notifications.router import get_notifications_service
from app.modules.notifications.schemas import NotificationList, NotificationRead
from app.modules.notifications.service import NotificationsService
from app.modules.telegram.service import TelegramDeliveryError


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, _: object) -> None:
        return None


class FakeTelegramService:
    def __init__(self, *, error: TelegramDeliveryError | None = None) -> None:
        self.error = error
        self.messages: list[str] = []
        self.photos: list[tuple[str, str | None]] = []
        self.parse_modes: list[str | None] = []
        self.photo_parse_modes: list[str | None] = []

    async def send_seller_notification(
        self,
        message: str,
        *,
        parse_mode: str | None = None,
    ) -> None:
        self.messages.append(message)
        self.parse_modes.append(parse_mode)
        if self.error is not None:
            raise self.error

    async def send_seller_photo(
        self,
        photo: str,
        *,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> None:
        self.photos.append((photo, caption))
        self.photo_parse_modes.append(parse_mode)
        if self.error is not None:
            raise self.error


class FakeNotificationsRepository:
    def __init__(self) -> None:
        self.notifications: dict[int, Notification] = {}
        self.next_notification_id = 1

    def add(self, notification: Notification) -> None:
        notification.id = self.next_notification_id
        self.next_notification_id += 1
        notification.created_at = _now()
        notification.updated_at = _now()
        self.notifications[notification.id] = notification

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        channel: NotificationChannel | None = None,
        status: NotificationStatus | None = None,
        user_id: int | None = None,
    ) -> tuple[list[Notification], int]:
        items = list(self.notifications.values())
        if channel is not None:
            items = [item for item in items if item.channel == channel]
        if status is not None:
            items = [item for item in items if item.status == status]
        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        return items[offset : offset + limit], len(items)

    async def get_by_id(self, notification_id: int) -> Notification | None:
        return self.notifications.get(notification_id)


@pytest.mark.asyncio
async def test_order_created_event_creates_and_sends_seller_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "public_seller_panel_base_url", "https://seller.stylexac.ru/")
    service, repository, session, telegram = _notifications_service()

    notification = await service.create_for_event(
        name=ORDER_CREATED,
        payload=_order_created_payload(),
    )

    assert notification is not None
    stored = repository.notifications[1]
    assert stored.type == ORDER_CREATED
    assert stored.channel == NotificationChannel.TELEGRAM
    assert stored.status == NotificationStatus.SENT
    assert stored.sent_at is not None
    assert len(telegram.messages) == 1
    message = telegram.messages[0]
    assert "<b>🛍 Новый заказ #ORD-00000001</b>" in message
    assert "ID заказа: 1" in message
    assert "ID клиента: 1" in message
    assert "Клиент" in message
    assert "Товары" in message
    assert "Промокод: SAVE10" in message
    assert "Скидка: 20 ₽" in message
    assert "К оплате: 99,80 ₽" in message
    assert "Способ доставки: СДЭК" in message
    assert "Панель продавца: https://seller.stylexac.ru/orders" in message
    assert telegram.parse_modes == ["HTML"]
    assert session.commits == 2


@pytest.mark.asyncio
async def test_order_created_seller_notification_splits_long_messages() -> None:
    service, _, _, telegram = _notifications_service()
    payload = _detailed_order_created_payload()
    payload["items"] = [
        {
            "product_id": index,
            "product_title": f"Long Product {index} " + ("x" * 80),
            "product_link": f"https://mini.stylexac.ru/product/{index}",
            "product_image_url": None,
            "variant_size": "XL",
            "variant_color": "White",
            "variant_sku": f"SKU-{index}",
            "quantity": 2,
            "unit_price": "100.00",
            "item_total": "200.00",
        }
        for index in range(1, 90)
    ]

    notification = await service.create_for_event(name=ORDER_CREATED, payload=payload)

    assert notification is not None
    assert len(telegram.messages) > 1
    assert all(len(message) <= 4096 for message in telegram.messages)


@pytest.mark.asyncio
async def test_order_created_seller_notification_can_send_photo_caption() -> None:
    service, _, _, telegram = _notifications_service()

    notification = await service.create_for_event(
        name=ORDER_CREATED,
        payload=_detailed_order_created_payload(),
    )

    assert notification is not None
    assert telegram.messages == []
    assert telegram.photos
    photo_url, caption = telegram.photos[0]
    assert photo_url == "https://api.stylexac.ru/uploads/products/hoodie.jpg"
    assert caption is not None
    assert caption.startswith("<b>🛍 Новый заказ #ORD-00000001</b>")
    assert "ID товара: 10" in caption
    assert "Фото: https://api.stylexac.ru/uploads/products/hoodie.jpg" in caption
    assert telegram.photo_parse_modes == ["HTML"]


@pytest.mark.asyncio
async def test_order_created_seller_notification_formats_eu_shoe_size() -> None:
    service, _, _, telegram = _notifications_service()
    payload = _detailed_order_created_payload()
    item = payload["items"][0]
    item["variant_size"] = "39"
    item["variant_size_grid"] = "shoes_eu"

    notification = await service.create_for_event(name=ORDER_CREATED, payload=payload)

    assert notification is not None
    assert telegram.photos
    assert "Размер: EU 39" in (telegram.photos[0][1] or "")


@pytest.mark.asyncio
async def test_order_created_seller_notification_formats_legacy_ru_shoe_size() -> None:
    service, _, _, telegram = _notifications_service()
    payload = _detailed_order_created_payload()
    item = payload["items"][0]
    item["variant_size"] = "39"
    item["variant_size_grid"] = "shoes_ru"

    notification = await service.create_for_event(name=ORDER_CREATED, payload=payload)

    assert notification is not None
    assert telegram.photos
    assert "Размер: RU 39" in (telegram.photos[0][1] or "")


@pytest.mark.asyncio
async def test_telegram_send_failure_marks_notification_failed() -> None:
    service, repository, session, _ = _notifications_service(
        telegram_error=TelegramDeliveryError("Telegram unavailable"),
    )

    notification = await service.create_for_event(
        name=ORDER_CREATED,
        payload=_order_created_payload(),
    )

    assert notification is not None
    stored = repository.notifications[1]
    assert stored.status == NotificationStatus.FAILED
    assert stored.error_message == "Telegram unavailable"
    assert stored.sent_at is None
    assert session.rolled_back is False


@pytest.mark.asyncio
async def test_promo_used_event_creates_internal_notification() -> None:
    service, repository, _, telegram = _notifications_service()

    notification = await service.create_for_event(
        name=PROMO_USED,
        payload={
            "order_id": 1,
            "order_number": "ORD-00000001",
            "user_id": 1,
            "promo_code": "SAVE10",
            "discount_amount": "20.00",
        },
    )

    assert notification is not None
    stored = repository.notifications[1]
    assert stored.user_id == 1
    assert stored.type == PROMO_USED
    assert stored.channel == NotificationChannel.INTERNAL
    assert stored.status == NotificationStatus.SENT
    assert stored.sent_at is not None
    assert telegram.messages == []


@pytest.mark.asyncio
async def test_order_status_changed_event_creates_seller_notification() -> None:
    service, repository, _, telegram = _notifications_service()

    notification = await service.create_for_event(
        name=ORDER_STATUS_CHANGED,
        payload={
            "order_id": 1,
            "order_number": "ORD-00000001",
            "user_id": 1,
            "previous_status": "NEW",
            "new_status": "PROCESSING",
        },
    )

    assert notification is not None
    stored = repository.notifications[1]
    assert stored.type == ORDER_STATUS_CHANGED
    assert stored.channel == NotificationChannel.TELEGRAM
    assert stored.status == NotificationStatus.SENT
    assert telegram.messages == [
        "🔄 Статус заказа изменён\n\n"
        "Заказ: ORD-00000001\n"
        "Было: Новый\n"
        "Стало: В обработке"
    ]


@pytest.mark.asyncio
async def test_order_shipped_event_creates_internal_user_notification() -> None:
    service, repository, _, telegram = _notifications_service()

    notification = await service.create_for_event(
        name=ORDER_SHIPPED,
        payload={
            "order_id": 1,
            "order_number": "ORD-00000001",
            "user_id": 1,
            "status": "SHIPPED",
        },
    )

    assert notification is not None
    stored = repository.notifications[1]
    assert stored.user_id == 1
    assert stored.type == ORDER_SHIPPED
    assert stored.channel == NotificationChannel.INTERNAL
    assert stored.status == NotificationStatus.SENT
    assert telegram.messages == []


@pytest.mark.asyncio
async def test_failed_telegram_notification_retry_sends_again() -> None:
    service, repository, _, telegram = _notifications_service()
    failed = _notification(status=NotificationStatus.FAILED)
    repository.add(failed)

    retried = await service.retry_notification(1)

    assert retried.status == NotificationStatus.SENT
    assert repository.notifications[1].error_message is None
    assert telegram.messages == [
        "<b>New order ORD-00000001</b>\n\nOrder ORD-00000001 was created."
    ]
    assert telegram.parse_modes == ["HTML"]


def test_seller_admin_can_list_notifications() -> None:
    app = create_app()

    class FakeNotificationsService:
        async def list_notifications(
            self,
            *,
            limit: int,
            offset: int,
            channel: NotificationChannel | None = None,
            status: NotificationStatus | None = None,
        ) -> NotificationList:
            del channel, status
            return NotificationList(
                items=[_notification_read()],
                meta=PageMeta(limit=limit, offset=offset, total=1),
            )

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_notifications_service] = lambda: FakeNotificationsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/notifications/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["type"] == ORDER_CREATED


def test_normal_user_cannot_list_admin_notifications() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/notifications/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_notification_admin_routes_require_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/notifications/admin")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def _notifications_service(
    *,
    telegram_error: TelegramDeliveryError | None = None,
) -> tuple[NotificationsService, FakeNotificationsRepository, DummySession, FakeTelegramService]:
    session = DummySession()
    telegram = FakeTelegramService(error=telegram_error)
    service = NotificationsService(session, telegram_service=telegram)
    repository = FakeNotificationsRepository()
    service.repository = repository
    return service, repository, session, telegram


def _notification(status: NotificationStatus = NotificationStatus.SENT) -> Notification:
    return Notification(
        id=1,
        user_id=None,
        type=ORDER_CREATED,
        title="New order ORD-00000001",
        message="Order ORD-00000001 was created.",
        payload=_order_created_payload(),
        channel=NotificationChannel.TELEGRAM,
        status=status,
        error_message="Telegram unavailable" if status == NotificationStatus.FAILED else None,
        sent_at=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _notification_read() -> NotificationRead:
    return NotificationRead.model_validate(_notification())


def _order_created_payload() -> dict[str, object]:
    return {
        "order_id": 1,
        "order_number": "ORD-00000001",
        "user_id": 1,
        "subtotal_amount": "119.80",
        "discount_amount": "20.00",
        "total_amount": "99.80",
        "promo_code_id": 7,
        "promo_code": "SAVE10",
        "customer": {
            "user_id": 1,
            "telegram_id": 42,
            "username": "buyer",
            "first_name": "Ada",
            "last_name": None,
            "name": "Ada",
        },
        "contact": {
            "name": "Ada",
            "phone": "+79990000000",
            "delivery_method": "CDEK",
            "delivery_method_label": "СДЭК",
            "delivery_address": "Moscow",
            "delivery_comment": "Call first",
        },
    }


def _detailed_order_created_payload() -> dict[str, object]:
    payload = _order_created_payload()
    payload.update(
        {
            "status": "NEW",
            "payment_status": "PENDING",
            "created_at": "2026-05-27T12:00:00+00:00",
            "customer": {
                "user_id": 1,
                "telegram_id": 42,
                "username": "buyer",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "name": "Ada Lovelace",
            },
            "items": [
                {
                    "product_id": 10,
                    "product_title": "Hoodie",
                    "product_link": "https://mini.stylexac.ru/product/10",
                    "product_image_url": "https://api.stylexac.ru/uploads/products/hoodie.jpg",
                    "variant_size": "M",
                    "variant_color": "White",
                    "variant_sku": "HD-M-W",
                    "quantity": 1,
                    "unit_price": "99.80",
                    "item_total": "99.80",
                }
            ],
            "contact": {
                "name": "Ada",
                "phone": "+79990000000",
                "delivery_method": "CDEK",
                "delivery_method_label": "СДЭК",
                "delivery_address": "Moscow",
                "delivery_comment": "Call first",
            },
            "seller_panel_url": "https://seller.stylexac.ru/orders",
        }
    )
    return payload


def _user(role: UserRole) -> User:
    return User(
        id=1,
        telegram_id=42,
        username="seller",
        first_name="Ada",
        last_name=None,
        phone=None,
        role=role,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 5, 27, tzinfo=UTC)
