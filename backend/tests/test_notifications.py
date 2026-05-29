from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.common.pagination import PageMeta
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

    async def send_seller_notification(self, message: str) -> None:
        self.messages.append(message)
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
async def test_order_created_event_creates_and_sends_seller_notification() -> None:
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
    assert telegram.messages == [
        "New order ORD-00000001\n\nOrder ORD-00000001 was created. Total: 99.80."
    ]
    assert session.commits == 2


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
        "Order ORD-00000001 status changed\n\n"
        "Order ORD-00000001 changed from NEW to PROCESSING."
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
    assert telegram.messages == ["New order ORD-00000001\n\nOrder ORD-00000001 was created."]


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
    }


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
