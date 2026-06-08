from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.common.pagination import PageMeta
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    NotificationChannel,
    NotificationStatus,
    ProductStatus,
    SellerCredential,
    User,
    UserRole,
)
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
from app.modules.telegram.service import TelegramDownloadedFile


class DummySession:
    def __init__(self) -> None:
        self.commits = 0
        self.rolled_back = False
        self.flushed = False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rolled_back = True

    async def flush(self) -> None:
        self.flushed = True


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


class FakeQuickProductRepository:
    def __init__(self) -> None:
        self.products: list[object] = []
        self.next_id = 101

    def add(self, product: object) -> None:
        product.id = self.next_id
        self.next_id += 1
        self.products.append(product)


class FakeQuickVariantRepository:
    def __init__(self) -> None:
        self.variants: list[object] = []

    def add(self, variant: object) -> None:
        self.variants.append(variant)


class FakeQuickCategoryRepository:
    async def get_by_name_or_slug(self, _: str) -> None:
        return None


class FakeQuickTagsRepository:
    async def list_by_names_or_slugs(self, _: list[str]) -> list[object]:
        return []


class FakeQuickStorage:
    def __init__(self) -> None:
        self.saved: list[tuple[bytes, str, str]] = []
        self.deleted: list[str] = []

    def save_bytes(self, content: bytes, *, folder: str, suffix: str) -> str:
        self.saved.append((content, folder, suffix))
        return "products/telegram-photo.jpg"

    def delete(self, relative_path: str) -> None:
        self.deleted.append(relative_path)


class FakeQuickTelegramService:
    async def download_file(self, file_id: str) -> TelegramDownloadedFile:
        assert file_id == "photo-large"
        return TelegramDownloadedFile(
            content=b"image-bytes",
            file_path="photos/file_1.jpg",
            original_filename="file_1.jpg",
            mime_type="image/jpeg",
            extension=".jpg",
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
async def test_unblock_seller_reactivates_user_and_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, repository, audit = _seller_bot_command_service()
    repository.user.is_active = False

    message = await service.unblock_seller_command(
        chat_id=-100,
        target_user_id=repository.user.id,
        actor_telegram_user_id=500,
        actor_username="approver",
    )

    assert message == "Seller #1 has been unblocked."
    assert repository.user.is_active is True
    assert audit.records[0]["action"] == "seller_unblocked"


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


@pytest.mark.asyncio
async def test_new_product_command_creates_draft_with_photo_and_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, variant_repository, storage, audit = _quick_product_service()

    message = await service.create_quick_product_draft_command(
        chat_id=-100,
        message=_quick_product_message(),
        actor_telegram_user_id=500,
        actor_username="operator",
    )

    product = product_repository.products[0]
    assert product.name == "White Hoodie"
    assert product.base_price == "1990.00" or str(product.base_price) == "1990.00"
    assert product.status == ProductStatus.DRAFT
    assert product.images[0].file_path == "products/telegram-photo.jpg"
    assert product.images[0].is_primary is True
    assert [variant.size for variant in variant_repository.variants] == ["M", "L"]
    assert [variant.color for variant in variant_repository.variants] == ["White", "White"]
    assert [variant.stock_quantity for variant in variant_repository.variants] == [5, 5]
    assert variant_repository.variants[0].sku == "HD-W-M"
    assert "Product ID: 101" in message
    assert "Status: DRAFT" in message
    assert "https://seller.tsplatform.ru/products/101/edit" in message
    assert storage.saved == [(b"image-bytes", "products", ".jpg")]
    assert audit.records[0]["action"] == "bot_product_draft_created"


@pytest.mark.asyncio
async def test_new_product_command_rejects_missing_photo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, audit = _quick_product_service()

    with pytest.raises(AppError, match="Attach one product photo"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(photo=False),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert audit.records[0]["action"] == "bot_product_post_rejected"


@pytest.mark.asyncio
async def test_new_product_command_rejects_missing_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, audit = _quick_product_service()

    with pytest.raises(AppError, match="Missing required field"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(caption="/new_product\nЦена: 100"),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert audit.records[0]["action"] == "bot_product_post_rejected"


@pytest.mark.asyncio
async def test_new_product_command_rejects_invalid_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, audit = _quick_product_service()

    with pytest.raises(AppError, match="valid price"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption="/new_product\nНазвание: Hoodie\nЦена: nope",
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert audit.records[0]["action"] == "bot_product_post_rejected"


@pytest.mark.asyncio
async def test_new_product_command_rejects_unauthorized_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, audit = _quick_product_service()

    with pytest.raises(AppError, match="seller group"):
        await service.create_quick_product_draft_command(
            chat_id=100,
            message=_quick_product_message(),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert audit.records == []


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


def _quick_product_service() -> tuple[
    SellerBotService,
    FakeQuickProductRepository,
    FakeQuickVariantRepository,
    FakeQuickStorage,
    FakeAuditService,
]:
    telegram = FakeQuickTelegramService()
    service = SellerBotService(DummySession(), telegram_service=telegram)
    product_repository = FakeQuickProductRepository()
    variant_repository = FakeQuickVariantRepository()
    storage = FakeQuickStorage()
    audit = FakeAuditService()
    service.products_repository = product_repository
    service.variants_repository = variant_repository
    service.categories_repository = FakeQuickCategoryRepository()
    service.tags_repository = FakeQuickTagsRepository()
    service.storage = storage
    service.audit_service = audit
    return service, product_repository, variant_repository, storage, audit


def _quick_product_message(
    *,
    caption: str | None = None,
    photo: bool = True,
):
    from app.modules.telegram.schemas import TelegramMessage

    payload = {
        "message_id": 30,
        "caption": caption
        or "\n".join(
            (
                "/new_product",
                "Название: White Hoodie",
                "Цена: 1990",
                "Старая цена: 2490",
                "Описание: Warm cotton hoodie",
                "Категория: Hoodies",
                "Теги: hoodie, winter",
                "Размеры: M,L",
                "Цвет: White",
                "SKU: HD-W",
                "Остаток: 5",
                "Приоритет поиска: 1",
                "Ключевые слова: hoodie, white hoodie",
                "Статус: DRAFT",
            )
        ),
        "chat": {"id": -100, "type": "supergroup"},
        "from": {"id": 500, "username": "operator"},
    }
    if photo:
        payload["photo"] = [
            {"file_id": "photo-small", "width": 90, "height": 90, "file_size": 1000},
            {"file_id": "photo-large", "width": 1200, "height": 1500, "file_size": 500000},
        ]
    return TelegramMessage.model_validate(payload)


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
