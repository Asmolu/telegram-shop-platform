from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.common.pagination import PageMeta
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import NotificationChannel, NotificationStatus, SellerCredential, User, UserRole
from app.main import create_app
from app.modules.notifications.schemas import NotificationList, NotificationRead
from app.modules.seller_bot.router import get_seller_bot_service
from app.modules.seller_bot.schemas import (
    SellerBotActionResponse,
    SellerBotBroadcastRequest,
    SellerBotMessageRequest,
    SellerBotStatusResponse,
)
from app.modules.seller_bot.service import SellerBotService


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeSellerBotRepository:
    def __init__(self) -> None:
        self.requested_user_ids: list[int] = []
        self.user = _user(UserRole.SELLER)
        self.credential = SellerCredential(
            id=1,
            user_id=self.user.id,
            user=self.user,
            email="seller@example.com",
            password_hash="not-exposed",
            telegram_username="seller",
            telegram_user_id=42,
            telegram_chat_id=42,
            verified_at=_now(),
            created_at=_now(),
            updated_at=_now(),
        )

    async def list_sellers(self, *, limit: int):
        assert limit == 20
        return [(self.user, self.credential)], 1

    async def get_seller_user(self, user_id: int) -> User | None:
        self.requested_user_ids.append(user_id)
        if user_id == self.user.id:
            return self.user
        return None


class FakeAuditService:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record_action(self, **kwargs) -> None:
        self.records.append(kwargs)


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


@pytest.mark.asyncio
async def test_sellers_command_lists_sellers_in_seller_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, _ = _seller_bot_command_service()

    message = await service.format_sellers_command(chat_id=-100)

    assert "Seller ID for commands: 1" in message
    assert "Email: seller@example.com" in message
    assert "Telegram user/chat: 42 / 42" in message
    assert "Role: SELLER" in message
    assert "Status: active" in message
    assert "Use /block_seller <Seller ID>, for example: /block_seller 5" in message
    assert "Do not use Telegram user id/chat id." in message
    assert repository.credential.password_hash not in message


@pytest.mark.asyncio
async def test_sellers_command_rejects_outside_seller_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _, _ = _seller_bot_command_service()

    with pytest.raises(AppError, match="seller group"):
        await service.format_sellers_command(chat_id=100)


@pytest.mark.asyncio
async def test_block_seller_deactivates_user_and_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, audit = _seller_bot_command_service()

    message = await service.block_seller_command(
        chat_id=-100,
        target_user_id=repository.user.id,
        actor_telegram_user_id=500,
        actor_username="approver",
    )

    assert message == "Seller #1 has been blocked."
    assert repository.user.is_active is False
    assert audit.records[0]["action"] == "seller_bot.block_seller"


@pytest.mark.asyncio
async def test_block_seller_rejects_outside_seller_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, _ = _seller_bot_command_service()

    with pytest.raises(AppError, match="seller group"):
        await service.block_seller_command(
            chat_id=100,
            target_user_id=repository.user.id,
            actor_telegram_user_id=500,
            actor_username="approver",
        )


@pytest.mark.asyncio
async def test_block_seller_rejects_oversized_internal_id_before_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, _ = _seller_bot_command_service()

    with pytest.raises(AppError, match="outside the supported range"):
        await service.block_seller_command(
            chat_id=-100,
            target_user_id=2_147_483_648,
            actor_telegram_user_id=500,
            actor_username="approver",
        )

    assert repository.requested_user_ids == []


def _seller_bot_command_service() -> tuple[
    SellerBotService,
    FakeSellerBotRepository,
    FakeAuditService,
]:
    service = SellerBotService(DummySession())
    repository = FakeSellerBotRepository()
    audit = FakeAuditService()
    service.repository = repository
    service.audit_service = audit
    return service, repository, audit


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
