from datetime import UTC, datetime
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.common.pagination import PageMeta
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    Category,
    NotificationChannel,
    NotificationStatus,
    ProductImageBadgeType,
    ProductSizeGrid,
    ProductStatus,
    SellerCredential,
    Tag,
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
        self.existing_ids = {11, 12, 13}

    async def list_existing_ids(self, product_ids: list[int]) -> set[int]:
        return set(product_ids) & self.existing_ids

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
    def __init__(self) -> None:
        self.categories = [
            Category(id=1, name="Hoodies", slug="hoodies", description=None),
            Category(id=2, name="Футболки", slug="t-shirts", description=None),
            Category(id=3, name="Обувь", slug="shoes", description=None),
        ]

    async def get_by_name_or_slug(self, value: str) -> Category | None:
        normalized = value.strip().casefold()
        return next(
            (
                category
                for category in self.categories
                if category.name.casefold() == normalized or category.slug == normalized
            ),
            None,
        )

    async def get_by_id(self, category_id: int) -> Category | None:
        return next(
            (category for category in self.categories if category.id == category_id),
            None,
        )


class FakeQuickTagsRepository:
    def __init__(self) -> None:
        names = ("hoodie", "winter", "футболка", "hermes", "кроссовки", "nike", "premium")
        self.tags = [Tag(id=index, name=name, slug=name) for index, name in enumerate(names, 1)]

    async def list_by_names_or_slugs(self, values: list[str]) -> list[Tag]:
        normalized = {value.strip().casefold() for value in values}
        return [
            tag
            for tag in self.tags
            if tag.name.casefold() in normalized or tag.slug.casefold() in normalized
        ]

    async def list_by_ids(self, tag_ids: list[int]) -> list[Tag]:
        return [tag for tag in self.tags if tag.id in tag_ids]


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
    prepared_sizes: list[str] = []
    prepare_variant = service.products_service.prepare_product_variant

    def track_prepared_variant(**kwargs):
        prepared_sizes.append(kwargs["payload"].size)
        return prepare_variant(**kwargs)

    monkeypatch.setattr(service.products_service, "prepare_product_variant", track_prepared_variant)

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
    assert product.size_grid == ProductSizeGrid.CLOTHING_ALPHA
    assert product.images[0].file_path == "products/telegram-photo.jpg"
    assert product.images[0].is_primary is True
    assert [variant.size for variant in variant_repository.variants] == ["M", "L", "3XL"]
    assert [variant.color for variant in variant_repository.variants] == [
        "White",
        "White",
        "Black",
    ]
    assert [variant.stock_quantity for variant in variant_repository.variants] == [5, 5, 3]
    assert variant_repository.variants[0].sku == "HD-W-M"
    assert prepared_sizes == ["M", "L", "3XL"]
    assert "ID: 101" in message
    assert "Статус: черновик" in message
    assert "https://seller.tsplatform.ru/products/101/edit" in message
    assert storage.saved == [(b"image-bytes", "products", ".jpg")]
    assert audit.records[0]["action"] == "bot_product_draft_created"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("badge_value", "expected_type", "expected_label"),
    [
        ("Распродажа", ProductImageBadgeType.SALE, "Распродажа"),
        ("NEW", ProductImageBadgeType.NEW, "NEW"),
    ],
)
async def test_new_product_command_creates_related_products_and_preset_badge(
    monkeypatch: pytest.MonkeyPatch,
    badge_value: str,
    expected_type: ProductImageBadgeType,
    expected_label: str,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, _ = _quick_product_service()

    message = await service.create_quick_product_draft_command(
        chat_id=-100,
        message=_quick_product_message(
            caption=_strict_product_caption(
                title="Related Hoodie",
                size_grid="одежда",
                rows=("3XL / Black / 2 / RELATED-3XL",),
                related_products="11, 12, 13",
                image_badge=badge_value,
            )
        ),
        actor_telegram_user_id=500,
        actor_username="operator",
    )

    product = product_repository.products[0]
    assert product.related_product_ids == [11, 12, 13]
    assert product.image_badge_type == expected_type
    assert product.image_badge_text is None
    assert f"Виджет фото: {expected_label}" in message
    assert "Похожие товары: 11, 12, 13" in message


@pytest.mark.asyncio
async def test_new_product_command_creates_custom_badge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, _ = _quick_product_service()

    message = await service.create_quick_product_draft_command(
        chat_id=-100,
        message=_quick_product_message(
            caption=_strict_product_caption(
                title="Custom Badge Hoodie",
                size_grid="одежда",
                rows=("M / White / 2 / CUSTOM-M",),
                image_badge="custom",
                image_badge_text="-30%",
            )
        ),
        actor_telegram_user_id=500,
        actor_username="operator",
    )

    product = product_repository.products[0]
    assert product.image_badge_type == ProductImageBadgeType.CUSTOM
    assert product.image_badge_text == "-30%"
    assert "Виджет фото: custom (-30%)" in message


@pytest.mark.asyncio
async def test_new_product_command_rejects_unknown_related_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, storage, _ = _quick_product_service()

    with pytest.raises(AppError, match="похожие товары не найдены: 999"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Unknown Related Hoodie",
                    size_grid="одежда",
                    rows=("M / White / 2 / UNKNOWN-M",),
                    related_products="11, 999",
                )
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert storage.deleted == ["products/telegram-photo.jpg"]


@pytest.mark.asyncio
async def test_new_product_command_rejects_duplicate_related_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, storage, _ = _quick_product_service()

    with pytest.raises(AppError, match="повторяющиеся ID"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Duplicate Related Hoodie",
                    size_grid="одежда",
                    rows=("M / White / 2 / DUPLICATE-M",),
                    related_products="11, 12, 11",
                )
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert storage.saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("badge_text", "expected"),
    [
        (None, "добавь непустое поле"),
        ("123456789012345678901", "не длиннее 20 символов"),
        ("<b>sale</b>", "не должно содержать HTML"),
    ],
)
async def test_new_product_command_rejects_invalid_custom_badge_text(
    monkeypatch: pytest.MonkeyPatch,
    badge_text: str | None,
    expected: str,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, storage, _ = _quick_product_service()

    with pytest.raises(AppError, match=expected):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Invalid Custom Badge",
                    size_grid="одежда",
                    rows=("M / White / 2 / INVALID-CUSTOM-M",),
                    image_badge="custom",
                    image_badge_text=badge_text,
                )
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert storage.saved == []


@pytest.mark.asyncio
async def test_new_product_command_creates_footwear_with_boundary_sizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, variant_repository, _, _ = _quick_product_service()

    await service.create_quick_product_draft_command(
        chat_id=-100,
        message=_quick_product_message(
            caption=_strict_product_caption(
                title="Boundary Shoes",
                size_grid="обувь",
                rows=("35 / White / 2 / SHOE-35", "46 / Black / 1 / SHOE-46"),
                categories="Обувь",
                tags="кроссовки, nike",
            )
        ),
        actor_telegram_user_id=500,
        actor_username="operator",
    )

    assert product_repository.products[0].size_grid == ProductSizeGrid.SHOES_RU
    assert [variant.size for variant in variant_repository.variants] == ["35", "46"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_size", ["M", "RU 39", "39.5", "47"])
async def test_new_product_command_rejects_invalid_footwear_sizes(
    monkeypatch: pytest.MonkeyPatch,
    invalid_size: str,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _, variant_repository, _, _ = _quick_product_service()

    with pytest.raises(AppError, match="недопустим для обуви"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Invalid Shoes",
                    size_grid="обувь",
                    rows=(f"{invalid_size} / White / 2 / BAD-SHOE",),
                )
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert variant_repository.variants == []


@pytest.mark.asyncio
async def test_new_product_command_rejects_numeric_clothing_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _, variant_repository, _, _ = _quick_product_service()

    with pytest.raises(AppError, match="недопустим для одежды"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Invalid Shirt",
                    size_grid="одежда",
                    rows=("42 / White / 2 / SHIRT-42",),
                )
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert variant_repository.variants == []


@pytest.mark.asyncio
async def test_new_product_command_rejects_duplicate_size_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, storage, _ = _quick_product_service()

    with pytest.raises(AppError, match="дубликат комбинации"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Duplicate Shirt",
                    size_grid="одежда",
                    rows=(
                        "M / White / 2 / SHIRT-M-W-1",
                        "m / white / 3 / SHIRT-M-W-2",
                    ),
                )
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert storage.saved == []


@pytest.mark.asyncio
async def test_new_product_command_rejects_missing_photo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, audit = _quick_product_service()

    with pytest.raises(AppError, match="Фото"):
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

    with pytest.raises(AppError, match="Название"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(caption="/new_product\nЦена: 100"),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert audit.records[0]["action"] == "bot_product_post_rejected"


@pytest.mark.asyncio
async def test_new_product_command_rejects_old_price_not_above_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, audit = _quick_product_service()

    with pytest.raises(AppError, match="Старая цена"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Hoodie",
                    size_grid="одежда",
                    rows=("M / White / 1 / HOODIE-M",),
                    price="100",
                    old_price="100",
                ),
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert audit.records[0]["action"] == "bot_product_post_rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize("price", ["0", "-10", "nope"])
async def test_new_product_command_rejects_invalid_price(
    monkeypatch: pytest.MonkeyPatch,
    price: str,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, _ = _quick_product_service()

    with pytest.raises(AppError, match="положительным числом"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Invalid Price",
                    size_grid="одежда",
                    rows=("M / White / 1 / PRICE-M",),
                    price=price,
                    old_price="",
                )
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []


@pytest.mark.asyncio
async def test_new_product_command_rejects_negative_stock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, _, _ = _quick_product_service()

    with pytest.raises(AppError, match="не меньше 0"):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(
                caption=_strict_product_caption(
                    title="Invalid Stock",
                    size_grid="одежда",
                    rows=("M / White / -1 / STOCK-M",),
                )
            ),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "field_value", "expected"),
    [
        ("Категории", "Unknown Category", "категория `Unknown Category` не найдена"),
        ("Теги", "unknown-tag", "теги не найдены: `unknown-tag`"),
    ],
)
async def test_new_product_command_rejects_unknown_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    field_value: str,
    expected: str,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, product_repository, _, storage, _ = _quick_product_service()
    caption = _strict_product_caption(
        title="Taxonomy Test",
        size_grid="одежда",
        rows=("M / White / 1 / TAX-M",),
    )
    caption = caption.replace(f"{field_name}:", f"{field_name}: {field_value}")

    with pytest.raises(AppError, match=expected):
        await service.create_quick_product_draft_command(
            chat_id=-100,
            message=_quick_product_message(caption=caption),
            actor_telegram_user_id=500,
            actor_username="operator",
        )

    assert product_repository.products == []
    assert storage.saved == []


def test_new_product_help_contains_clothing_and_footwear_examples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_seller_chat_id", "-100")
    service, _, _, _, _ = _quick_product_service()

    help_text = service.format_new_product_help_command(chat_id=-100)

    assert "Футболка HERMES" in help_text
    assert "Кроссовки Nike Air Max" in help_text
    root = ElementTree.fromstring(f"<root>{help_text}</root>")
    code_blocks = ["".join(block.itertext()) for block in root.findall(".//pre/code")]
    assert sum(block.startswith("/new_product") for block in code_blocks) == 2
    assert all("Похожие товары: 11, 12, 13" in block for block in code_blocks[:2])
    assert "Виджет фото: custom" in code_blocks[2]
    assert "XS, S, M, L, XL, XXL, 3XL, ONE_SIZE" in help_text
    assert "российские целые размеры 35-46" in help_text
    assert "RU/EU/US/UK" in help_text
    assert "Похожие товары указываются ID через запятую" in help_text
    assert "Виджет фото: нет, NEW, Распродажа, Хит, Эксклюзив, custom" in help_text
    assert "по умолчанию товар создаётся как черновик" in help_text.lower()
    assert "Traceback" not in help_text
    assert "secret" not in help_text.casefold()
    assert len(help_text) < 4096


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
    category_repository = FakeQuickCategoryRepository()
    tags_repository = FakeQuickTagsRepository()
    storage = FakeQuickStorage()
    audit = FakeAuditService()
    service.products_service.repository = product_repository
    service.products_service.variants_repository = variant_repository
    service.products_service.categories_repository = category_repository
    service.products_service.tags_repository = tags_repository
    service.categories_repository = category_repository
    service.tags_repository = tags_repository
    service.storage = storage
    service.audit_service = audit
    return service, product_repository, variant_repository, storage, audit


def _strict_product_caption(
    *,
    title: str,
    size_grid: str,
    rows: tuple[str, ...],
    price: str = "1990",
    old_price: str = "2490",
    categories: str = "",
    tags: str = "",
    related_products: str | None = None,
    image_badge: str | None = None,
    image_badge_text: str | None = None,
    status: str = "черновик",
) -> str:
    lines = [
        "/new_product",
        f"Название: {title}",
        f"Цена: {price}",
        f"Старая цена: {old_price}",
        f"Категории: {categories}",
        f"Теги: {tags}",
        f"Тип размеров: {size_grid}",
        "Размеры:",
        *rows,
    ]
    if related_products is not None:
        lines.append(f"Похожие товары: {related_products}")
    if image_badge is not None:
        lines.append(f"Виджет фото: {image_badge}")
    if image_badge_text is not None:
        lines.append(f"Текст виджета фото: {image_badge_text}")
    lines.append(f"Статус: {status}")
    return "\n".join(lines)


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
                "Категории: Hoodies",
                "Теги: hoodie, winter",
                "Тип размеров: одежда",
                "Размеры:",
                "M / White / 5 / HD-W-M",
                "L / White / 5 / HD-W-L",
                "3XL / Black / 3 / HD-B-3XL",
                "Приоритет поиска: 1",
                "Псевдонимы поиска: hoodie, white hoodie",
                "Статус: черновик",
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
