from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.common.pagination import PageMeta
from app.db.models import NotificationChannel, NotificationStatus, User, UserRole
from app.main import create_app
from app.modules.notifications.schemas import NotificationList, NotificationRead
from app.modules.seller_bot.router import get_seller_bot_service
from app.modules.seller_bot.schemas import (
    SellerBotActionResponse,
    SellerBotBroadcastRequest,
    SellerBotMessageRequest,
    SellerBotStatusResponse,
)


def test_seller_bot_status_allows_seller() -> None:
    app = create_app()

    class FakeSellerBotService:
        async def get_status(self) -> SellerBotStatusResponse:
            return SellerBotStatusResponse(
                configured=True,
                seller_chat_configured=True,
                ok=True,
                bot={"username": "seller_bot"},
            )

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_seller_bot_service] = lambda: FakeSellerBotService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/seller-bot/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["bot"]["username"] == "seller_bot"


def test_normal_user_cannot_access_seller_bot_management() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/seller-bot/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_unauthenticated_cannot_access_seller_bot_management() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/seller-bot/status")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_seller_can_send_test_bot_message() -> None:
    app = create_app()

    class FakeSellerBotService:
        async def send_test_message(
            self,
            *,
            payload: SellerBotMessageRequest,
            actor_user_id: int,
        ) -> SellerBotActionResponse:
            assert payload.message == "Ping"
            assert actor_user_id == 1
            return SellerBotActionResponse(notification_id=7, status="sent", message="Ping")

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_seller_bot_service] = lambda: FakeSellerBotService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/seller-bot/test-message", json={"message": "Ping"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["notification_id"] == 7


def test_broadcast_endpoint_is_protected_and_allows_admin() -> None:
    app = create_app()

    class FakeSellerBotService:
        async def broadcast(
            self,
            *,
            payload: SellerBotBroadcastRequest,
            actor_user_id: int,
        ) -> SellerBotActionResponse:
            assert payload.message == "Broadcast"
            assert actor_user_id == 1
            return SellerBotActionResponse(
                notification_id=8,
                status="sent",
                message="Broadcast",
            )

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.ADMIN)
    app.dependency_overrides[get_seller_bot_service] = lambda: FakeSellerBotService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/seller-bot/broadcast", json={"message": "Broadcast"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["notification_id"] == 8


def test_seller_bot_messages_reuse_notification_list() -> None:
    app = create_app()

    class FakeSellerBotService:
        async def list_messages(self, *, limit: int, offset: int) -> NotificationList:
            return NotificationList(
                items=[_notification_read()],
                meta=PageMeta(limit=limit, offset=offset, total=1),
            )

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_seller_bot_service] = lambda: FakeSellerBotService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/seller-bot/messages")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["type"] == "seller_bot.broadcast"


def _notification_read() -> NotificationRead:
    return NotificationRead(
        id=1,
        user_id=None,
        type="seller_bot.broadcast",
        title="Seller notification chat broadcast",
        message="Broadcast",
        payload={"target": "seller_notification_chat"},
        channel=NotificationChannel.TELEGRAM,
        status=NotificationStatus.SENT,
        error_message=None,
        sent_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


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
    return datetime(2026, 6, 1, tzinfo=UTC)
