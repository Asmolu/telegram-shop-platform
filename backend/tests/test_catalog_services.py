from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import (
    Category,
    Product,
    ProductCategory,
    ProductImage,
    ProductImageBadgeColor,
    ProductImageBadgePosition,
    ProductImageBadgeType,
    ProductRelatedProduct,
    ProductSizeGrid,
    ProductStatus,
    ProductVariant,
    Tag,
)
from app.modules.categories.schemas import CategoryCreate, CategoryRead, CategoryUpdate
from app.modules.categories.service import CategoriesService
from app.modules.products.inventory import calculate_available_quantity
from app.modules.products.repository import ProductsRepository
from app.modules.products.schemas import (
    ProductCardList,
    ProductCardRead,
    ProductCreate,
    ProductImageCreate,
    ProductPublicDetailRead,
    ProductRead,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.modules.products.search import (
    SEARCH_PRIORITY_DEFAULT,
    SearchSuggestionCandidate,
    expand_color_query,
    normalize_search_aliases,
    search_text_matches_query,
)
from app.modules.products.service import ProductsService
from app.modules.products.size_grids import (
    CLOTHING_ALPHA_SIZES,
    SHOES_EU_SIZES,
    SHOES_RU_SIZES,
    SizeGridValidationError,
    normalize_size,
)
from app.modules.tags.schemas import TagCreate, TagRead, TagUpdate
from app.modules.tags.service import TagsService
from app.modules.uploads.storage import LocalStorageService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.deleted = False
        self.flush_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False
        self.rollback_count += 1

    async def refresh(self, _: object) -> None:
        return None

    async def flush(self) -> None:
        self.flush_count += 1

    async def delete(self, _: object) -> None:
        self.deleted = True


class FailingCommitSession(DummySession):
    async def commit(self) -> None:
        raise RuntimeError("commit failed")


class InspectingFirstFlushSession(DummySession):
    def __init__(self, product_ref: dict[str, Product], *, assigned_id: int = 10) -> None:
        super().__init__()
        self.product_ref = product_ref
        self.assigned_id = assigned_id

    async def flush(self) -> None:
        self.flush_count += 1
        if self.flush_count == 1:
            product = self.product_ref["product"]
            assert "related_product_links" in product.__dict__
            assert list(product.related_product_links) == []
            product.id = self.assigned_id


class IntegrityErrorFlushSession(DummySession):
    async def flush(self) -> None:
        self.flush_count += 1
        raise IntegrityError("insert products", {}, Exception("duplicate slug"))


class EmptyQueryResult:
    def scalars(self) -> "EmptyQueryResult":
        return self

    def all(self) -> list[object]:
        return []

    def scalar_one(self) -> int:
        return 0


class CapturingQuerySession(DummySession):
    def __init__(self) -> None:
        super().__init__()
        self.statements: list[object] = []

    async def execute(self, statement: object) -> EmptyQueryResult:
        self.statements.append(statement)
        return EmptyQueryResult()


class FakeAnalyticsTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def track(self, event_name: str, **payload: object) -> None:
        self.events.append((event_name, payload))


class FakeAuditService:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    async def record_action(self, **payload: object) -> None:
        self.logs.append(payload)

    def snapshot(self, instance: object, fields: tuple[str, ...]) -> dict[str, object]:
        return {field: getattr(instance, field) for field in fields}


@pytest.mark.asyncio
async def test_category_service_crud_flow() -> None:
    category = _category()
    service = CategoriesService(DummySession())
    service.repository.add = lambda created: setattr(created, "id", 1)
    service.repository.get_by_id = AsyncMock(return_value=category)
    service.repository.delete = AsyncMock()

    created = await service.create_category(
        CategoryCreate(name="Hoodies", slug="hoodies", description=None)
    )
    updated = await service.update_category(1, CategoryUpdate(name="Premium Hoodies"))
    await service.delete_category(1)

    assert created.id == 1
    assert updated.name == "Premium Hoodies"
    service.repository.delete.assert_awaited_once_with(category)


@pytest.mark.asyncio
async def test_category_service_sets_and_clears_uploaded_image(tmp_path: Path) -> None:
    image_path = "categories/0123456789abcdef0123456789abcdef.jpg"
    (tmp_path / "categories").mkdir()
    (tmp_path / image_path).write_bytes(b"category-image")
    category = _category(image_path=image_path)
    service = CategoriesService(DummySession(), storage=LocalStorageService(tmp_path))
    service.repository.add = lambda created: setattr(created, "id", 1)
    service.repository.get_by_id = AsyncMock(return_value=category)

    created = await service.create_category(
        CategoryCreate(name="Hoodies", slug="hoodies", image_path=image_path)
    )
    updated = await service.update_category(1, CategoryUpdate(image_path=None))

    assert created.image_path == image_path
    assert created.image_url == f"/uploads/{image_path}"
    assert updated.image_path is None
    assert updated.image_url is None


@pytest.mark.asyncio
async def test_category_service_rejects_missing_uploaded_image(tmp_path: Path) -> None:
    service = CategoriesService(DummySession(), storage=LocalStorageService(tmp_path))

    with pytest.raises(AppError, match="was not uploaded") as exc_info:
        await service.create_category(
            CategoryCreate(
                name="Hoodies",
                slug="hoodies",
                image_path="categories/0123456789abcdef0123456789abcdef.jpg",
            )
        )

    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    "image_path",
    [
        "https://example.com/category.jpg",
        "categories/../../category.jpg",
        "tags/0123456789abcdef0123456789abcdef.jpg",
    ],
)
def test_category_schema_rejects_invalid_image_paths(image_path: str) -> None:
    with pytest.raises(ValidationError):
        CategoryCreate(name="Hoodies", slug="hoodies", image_path=image_path)


def test_category_read_exposes_image_url() -> None:
    image_path = "categories/0123456789abcdef0123456789abcdef.webp"

    result = CategoryRead.model_validate(_category(image_path=image_path))

    assert result.image_path == image_path
    assert result.image_url == f"/uploads/{image_path}"


@pytest.mark.asyncio
async def test_tag_service_crud_flow() -> None:
    tag = _tag()
    service = TagsService(DummySession())
    service.repository.add = lambda created: setattr(created, "id", 1)
    service.repository.get_by_id = AsyncMock(return_value=tag)
    service.repository.delete = AsyncMock()

    created = await service.create_tag(TagCreate(name="Premium", slug="premium"))
    updated = await service.update_tag(1, TagUpdate(name="Sale"))
    await service.delete_tag(1)

    assert created.id == 1
    assert updated.name == "Sale"
    service.repository.delete.assert_awaited_once_with(tag)


@pytest.mark.asyncio
async def test_tag_service_sets_and_clears_uploaded_image(tmp_path: Path) -> None:
    image_path = "tags/0123456789abcdef0123456789abcdef.jpg"
    (tmp_path / "tags").mkdir()
    (tmp_path / image_path).write_bytes(b"tag-image")
    tag = _tag(image_path=image_path)
    service = TagsService(DummySession(), storage=LocalStorageService(tmp_path))
    service.repository.add = lambda created: setattr(created, "id", 1)
    service.repository.get_by_id = AsyncMock(return_value=tag)

    created = await service.create_tag(
        TagCreate(name="Premium", slug="premium", image_path=image_path)
    )
    updated = await service.update_tag(1, TagUpdate(image_path=None))

    assert created.image_path == image_path
    assert created.image_url == f"/uploads/{image_path}"
    assert updated.image_path is None
    assert updated.image_url is None


@pytest.mark.asyncio
async def test_tag_service_rejects_missing_uploaded_image(tmp_path: Path) -> None:
    service = TagsService(DummySession(), storage=LocalStorageService(tmp_path))

    with pytest.raises(AppError, match="was not uploaded") as exc_info:
        await service.create_tag(
            TagCreate(
                name="Premium",
                slug="premium",
                image_path="tags/0123456789abcdef0123456789abcdef.jpg",
            )
        )

    assert exc_info.value.status_code == 400


def test_tag_schema_rejects_external_image_url() -> None:
    with pytest.raises(ValidationError):
        TagCreate(name="Premium", slug="premium", image_path="https://example.com/tag.jpg")


def test_tag_read_exposes_image_url() -> None:
    image_path = "tags/0123456789abcdef0123456789abcdef.webp"

    result = TagRead.model_validate(_tag(image_path=image_path))

    assert result.image_path == image_path
    assert result.image_url == f"/uploads/{image_path}"


@pytest.mark.asyncio
async def test_product_service_create_update_delete_flow() -> None:
    product = _product()
    service = ProductsService(DummySession())
    service.categories_repository.get_by_id = AsyncMock(return_value=_category())
    service.tags_repository.list_by_ids = AsyncMock(return_value=[_tag()])
    service.repository.add = lambda created: setattr(created, "id", 1)
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.repository.delete = AsyncMock()

    created = await service.create_product(
        ProductCreate(
            name="Hoodie",
            slug="hoodie",
            description="Warm",
            base_price=Decimal("59.90"),
            status=ProductStatus.DRAFT,
            category_id=1,
            tag_ids=[1],
            images=[
                ProductImageCreate(
                    file_path="products/hoodie.jpg",
                    alt_text="Hoodie",
                    is_primary=True,
                )
            ],
        )
    )
    updated = await service.update_product(1, ProductUpdate(status=ProductStatus.ACTIVE))
    await service.delete_product(1)

    assert created.id == 1
    assert updated.status == ProductStatus.ACTIVE
    service.repository.delete.assert_awaited_once_with(product)


@pytest.mark.asyncio
async def test_product_image_replacement_preserves_old_files_on_commit_failure(
    tmp_path: Path,
) -> None:
    old_paths = [
        "products/old.jpg",
        "products/old.thumbnail.webp",
        "products/old.card.webp",
        "products/old.detail.webp",
    ]
    for path in old_paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"old")
    product = _product()
    product.images = [
        ProductImage(
            id=1,
            product_id=product.id,
            file_path=old_paths[0],
            thumbnail_path=old_paths[1],
            card_path=old_paths[2],
            detail_path=old_paths[3],
        )
    ]
    service = ProductsService(
        FailingCommitSession(),
        storage=LocalStorageService(tmp_path),
    )
    service.repository.get_by_id = AsyncMock(return_value=product)

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.update_product(
            product.id,
            ProductUpdate(images=[ProductImageCreate(file_path="products/new.jpg")]),
        )

    for path in old_paths:
        assert (tmp_path / path).is_file()


@pytest.mark.asyncio
async def test_product_delete_removes_original_and_derivatives(tmp_path: Path) -> None:
    image_paths = [
        "products/old.jpg",
        "products/old.thumbnail.webp",
        "products/old.card.webp",
        "products/old.detail.webp",
    ]
    for path in image_paths:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"old")
    product = _product()
    product.images = [
        ProductImage(
            id=1,
            product_id=product.id,
            file_path=image_paths[0],
            thumbnail_path=image_paths[1],
            card_path=image_paths[2],
            detail_path=image_paths[3],
        )
    ]
    service = ProductsService(DummySession(), storage=LocalStorageService(tmp_path))
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.repository.delete = AsyncMock()

    await service.delete_product(product.id)

    for path in image_paths:
        assert not (tmp_path / path).exists()


@pytest.mark.asyncio
async def test_product_service_creates_updates_and_reads_brand() -> None:
    captured: dict[str, Product] = {}
    service = ProductsService(DummySession())
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])

    def capture_product(product: Product) -> None:
        product.id = 1
        product.created_at = datetime(2026, 5, 27, tzinfo=UTC)
        product.updated_at = datetime(2026, 5, 27, tzinfo=UTC)
        captured["product"] = product

    service.repository.add = capture_product
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    created = await service.create_product(
        ProductCreate(
            name="Hoodie",
            slug="hoodie-brand",
            brand="  ICON STORE  ",
            base_price=Decimal("59.90"),
        )
    )
    created_brand = created.brand
    updated = await service.update_product(1, ProductUpdate(brand="  Atelier  "))
    read_model = ProductRead.model_validate(updated)

    assert created_brand == "ICON STORE"
    assert updated.brand == "Atelier"
    assert read_model.brand == "Atelier"


@pytest.mark.asyncio
async def test_product_create_defaults_visibility_and_returnability() -> None:
    captured: dict[str, Product] = {}
    service = ProductsService(DummySession())
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])

    def capture_product(product: Product) -> None:
        product.id = 1
        product.created_at = datetime(2026, 5, 27, tzinfo=UTC)
        product.updated_at = datetime(2026, 5, 27, tzinfo=UTC)
        captured["product"] = product

    service.repository.add = capture_product
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    created = await service.create_product(
        ProductCreate(
            name="Listed Returnable Hoodie",
            slug="listed-returnable-hoodie",
            base_price=Decimal("59.90"),
        )
    )

    assert created.is_listed is True
    assert created.is_returnable is True


@pytest.mark.asyncio
async def test_product_update_persists_visibility_and_returnability() -> None:
    product = _product(is_listed=True, is_returnable=True)
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)

    updated = await service.update_product(
        product.id,
        ProductUpdate(is_listed=False, is_returnable=False),
    )

    assert updated.is_listed is False
    assert updated.is_returnable is False


@pytest.mark.asyncio
async def test_public_product_list_never_exposes_non_active_statuses() -> None:
    service = ProductsService(DummySession())
    service.repository.list_public_cards = AsyncMock(
        return_value=([_product(status=ProductStatus.DRAFT)], 1)
    )

    result = await service.list_public_products(
        limit=20,
        offset=0,
        status=ProductStatus.DRAFT,
    )

    assert result == ProductCardList(items=[], meta=PageMeta(limit=20, offset=0, total=0))
    service.repository.list_public_cards.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_product_list_loads_only_active_variants() -> None:
    service = ProductsService(DummySession())
    service.repository.list_public_cards = AsyncMock(
        return_value=([_product(status=ProductStatus.ACTIVE, variants=[_variant()])], 1)
    )

    result = await service.list_public_products(limit=20, offset=0)

    assert result.meta.total == 1
    service.repository.list_public_cards.assert_awaited_once_with(
        limit=20,
        offset=0,
        category_id=None,
        tag_id=None,
        status=ProductStatus.ACTIVE,
        search=None,
        size_grid=None,
        size=None,
        color=None,
    )
    assert isinstance(result.items[0], ProductCardRead)
    assert result.items[0].variants[0].available_quantity == 5


def test_product_card_dto_uses_card_image_and_omits_detail_fields() -> None:
    product = _product(status=ProductStatus.ACTIVE, variants=[_variant()])
    product.images = [
        ProductImage(
            id=1,
            product_id=product.id,
            file_path="products/source.jpg",
            thumbnail_path="products/source.thumbnail.webp",
            card_path="products/source.card.webp",
            detail_path="products/source.detail.webp",
            alt_text="Hoodie",
            position=0,
            is_primary=True,
            created_at=datetime(2026, 5, 27, tzinfo=UTC),
        )
    ]

    card = ProductCardRead.model_validate(product)
    payload = card.model_dump(mode="json")

    assert payload["image_url"] == "/uploads/products/source.card.webp"
    assert payload["thumbnail_image_url"] == "/uploads/products/source.thumbnail.webp"
    assert "description" not in payload
    assert "images" not in payload
    assert "detail_url" not in payload
    assert "sku" not in payload["variants"][0]


def test_public_detail_dto_keeps_variants_without_filesystem_paths() -> None:
    product = _product(status=ProductStatus.ACTIVE, variants=[_variant()])
    product.images = [
        ProductImage(
            id=1,
            product_id=product.id,
            file_path="products/source.jpg",
            thumbnail_path="products/source.thumbnail.webp",
            card_path="products/source.card.webp",
            detail_path="products/source.detail.webp",
            alt_text="Hoodie",
            position=0,
            is_primary=True,
            created_at=datetime(2026, 5, 27, tzinfo=UTC),
        )
    ]

    detail = ProductPublicDetailRead.model_validate(product)
    payload = detail.model_dump(mode="json")

    assert payload["images"][0]["detail_url"] == "/uploads/products/source.detail.webp"
    assert payload["images"][0]["image_variants"]["card"] == "/uploads/products/source.card.webp"
    assert "file_path" not in payload["images"][0]
    assert "thumbnail_path" not in payload["images"][0]
    assert payload["variants"][0]["sku"] == "HOODIE-M-BLK"
    assert "stock_quantity" not in payload["variants"][0]


@pytest.mark.asyncio
async def test_public_product_search_tracks_sanitized_query() -> None:
    tracker = FakeAnalyticsTracker()
    service = ProductsService(DummySession(), analytics_tracker=tracker)
    service.repository.list_public_cards = AsyncMock(return_value=([], 0))

    await service.list_public_products(limit=20, offset=0, search=" \n футболка \t ")

    assert tracker.events == [
        (
            "search.performed",
            {"user_id": None, "metadata": {"query": "футболка", "result_count": 0}},
        )
    ]


@pytest.mark.asyncio
async def test_product_search_suggestions_sanitize_limit_and_skip_analytics() -> None:
    tracker = FakeAnalyticsTracker()
    service = ProductsService(DummySession(), analytics_tracker=tracker)
    service.repository.list_search_suggestions = AsyncMock(
        return_value=[
            SearchSuggestionCandidate(value="Hoodie", kind="product", score=0),
            SearchSuggestionCandidate(value="ICON STORE", kind="brand", score=20),
        ]
    )

    result = await service.list_search_suggestions(query=" \n Hoodie \t ", limit=99)

    assert [item.value for item in result.items] == ["Hoodie", "ICON STORE"]
    assert [item.kind for item in result.items] == ["product", "brand"]
    service.repository.list_search_suggestions.assert_awaited_once_with(
        query="Hoodie",
        limit=10,
    )
    assert tracker.events == []


@pytest.mark.asyncio
async def test_product_search_suggestions_ignore_tiny_queries() -> None:
    service = ProductsService(DummySession())
    service.repository.list_search_suggestions = AsyncMock(return_value=[])

    result = await service.list_search_suggestions(query="h", limit=8)

    assert result.items == []
    service.repository.list_search_suggestions.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_product_detail_tracks_product_view() -> None:
    tracker = FakeAnalyticsTracker()
    service = ProductsService(DummySession(), analytics_tracker=tracker)
    service.repository.get_public_detail_by_id = AsyncMock(
        return_value=_product(status=ProductStatus.ACTIVE)
    )

    product = await service.get_public_product(1, user_id=None)

    assert product.id == 1
    assert isinstance(product, ProductPublicDetailRead)
    assert tracker.events == [
        (
            "product.viewed",
            {"user_id": None, "product_id": 1},
        )
    ]


@pytest.mark.asyncio
async def test_public_product_detail_returns_only_active_related_products() -> None:
    active_related = _product(product_id=2, status=ProductStatus.ACTIVE)
    inactive_related = _product(product_id=3, status=ProductStatus.DRAFT)
    unlisted_related = _product(product_id=4, status=ProductStatus.ACTIVE, is_listed=False)
    product = _product(status=ProductStatus.ACTIVE)
    product.related_product_links = [
        ProductRelatedProduct(
            product_id=product.id,
            related_product_id=active_related.id,
            position=0,
            related_product=active_related,
        ),
        ProductRelatedProduct(
            product_id=product.id,
            related_product_id=inactive_related.id,
            position=1,
            related_product=inactive_related,
        ),
        ProductRelatedProduct(
            product_id=product.id,
            related_product_id=unlisted_related.id,
            position=2,
            related_product=unlisted_related,
        ),
    ]
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_id = AsyncMock(return_value=product)

    result = await service.get_public_product(product.id)

    assert result.related_product_ids == [2]
    assert [item.id for item in result.related_products] == [2]


@pytest.mark.asyncio
async def test_public_product_detail_returns_active_unlisted_product_by_direct_id() -> None:
    product = _product(status=ProductStatus.ACTIVE, is_listed=False)
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_id = AsyncMock(return_value=product)

    result = await service.get_public_product(product.id, track_view=False)

    assert result.id == product.id
    assert result.name == product.name


@pytest.mark.asyncio
async def test_public_product_resolver_returns_product_without_category_or_sku() -> None:
    product = _product(status=ProductStatus.ACTIVE, variants=[_variant()])
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)

    result = await service.resolve_public_product(product_slug=product.slug, track_view=False)

    assert result.product.id == product.id
    assert result.route_context.product_slug == product.slug
    assert result.route_context.category is None
    assert result.route_context.variant_status == "sku_missing"
    assert result.route_context.selected_variant_id is None
    service.repository.get_public_detail_by_slug.assert_awaited_once_with(product.slug)


@pytest.mark.asyncio
async def test_public_product_resolver_accepts_numeric_product_slug_with_sku() -> None:
    variant = _variant(sku="00001")
    product = _product(status=ProductStatus.ACTIVE, variants=[variant])
    product.slug = "00042"
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)
    service.variants_repository.get_by_sku = AsyncMock(return_value=variant)

    result = await service.resolve_public_product(
        product_slug="00042",
        sku="00001",
        track_view=False,
    )

    assert result.product.slug == "00042"
    assert result.route_context.product_slug == "00042"
    assert result.route_context.selected_variant_sku == "00001"
    service.repository.get_public_detail_by_slug.assert_awaited_once_with("00042")


@pytest.mark.asyncio
async def test_public_product_resolver_accepts_each_assigned_category() -> None:
    primary = _category(category_id=1, name="T-shirts", slug="futbolki")
    secondary = _category(category_id=2, name="Summer", slug="leto")
    product = _product(status=ProductStatus.ACTIVE, variants=[_variant()])
    product.category_id = primary.id
    product.category = primary
    product.product_categories = [
        ProductCategory(category_id=primary.id, priority=1, category=primary),
        ProductCategory(category_id=secondary.id, priority=2, category=secondary),
    ]
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)
    service.categories_repository.get_by_slug = AsyncMock(side_effect=[primary, secondary])

    first = await service.resolve_public_product(
        product_slug=product.slug,
        category_slug=primary.slug,
        track_view=False,
    )
    second = await service.resolve_public_product(
        product_slug=product.slug,
        category_slug=secondary.slug,
        track_view=False,
    )

    assert first.route_context.category is not None
    assert first.route_context.category.slug == "futbolki"
    assert second.route_context.category is not None
    assert second.route_context.category.slug == "leto"


@pytest.mark.asyncio
async def test_public_product_resolver_rejects_missing_category() -> None:
    product = _product(status=ProductStatus.ACTIVE)
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)
    service.categories_repository.get_by_slug = AsyncMock(return_value=None)

    with pytest.raises(AppError, match="Product not found") as error:
        await service.resolve_public_product(
            product_slug=product.slug,
            category_slug="missing",
            track_view=False,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_public_product_resolver_rejects_unassigned_category() -> None:
    product = _product(status=ProductStatus.ACTIVE)
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)
    service.categories_repository.get_by_slug = AsyncMock(
        return_value=_category(category_id=99, slug="sale")
    )

    with pytest.raises(AppError, match="Product not found") as error:
        await service.resolve_public_product(
            product_slug=product.slug,
            category_slug="sale",
            track_view=False,
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_public_product_resolver_rejects_missing_product_slug() -> None:
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=None)

    with pytest.raises(AppError, match="Product not found") as error:
        await service.resolve_public_product(product_slug="missing", track_view=False)

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_public_product_resolver_selects_valid_sku() -> None:
    variant = _variant(sku="00001", stock_quantity=5, reserved_quantity=1)
    product = _product(status=ProductStatus.ACTIVE, variants=[variant])
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)
    service.variants_repository.get_by_sku = AsyncMock(return_value=variant)

    result = await service.resolve_public_product(
        product_slug=product.slug,
        sku=variant.sku,
        track_view=False,
    )

    assert result.route_context.variant_status == "selected"
    assert result.route_context.selected_variant_id == variant.id
    assert result.route_context.selected_variant_sku == "00001"


@pytest.mark.asyncio
async def test_public_product_resolver_selects_out_of_stock_sku() -> None:
    variant = _variant(sku="00001", stock_quantity=2, reserved_quantity=2)
    product = _product(status=ProductStatus.ACTIVE, variants=[variant])
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)
    service.variants_repository.get_by_sku = AsyncMock(return_value=variant)

    result = await service.resolve_public_product(
        product_slug=product.slug,
        sku=variant.sku,
        track_view=False,
    )

    assert result.route_context.variant_status == "out_of_stock"
    assert result.route_context.selected_variant_id == variant.id


@pytest.mark.asyncio
async def test_public_product_resolver_handles_sku_from_another_product() -> None:
    product = _product(status=ProductStatus.ACTIVE, variants=[_variant(sku="00001")])
    other_variant = _variant(sku="00002")
    other_variant.product_id = 2
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)
    service.variants_repository.get_by_sku = AsyncMock(return_value=other_variant)

    result = await service.resolve_public_product(
        product_slug=product.slug,
        sku=other_variant.sku,
        track_view=False,
    )

    assert result.product.id == product.id
    assert result.route_context.variant_status == "sku_not_for_product"
    assert result.route_context.selected_variant_id is None


@pytest.mark.asyncio
async def test_public_product_resolver_handles_missing_and_inactive_skus() -> None:
    product = _product(status=ProductStatus.ACTIVE, variants=[_variant(sku="00001")])
    inactive_variant = _variant(sku="00003", is_active=False)
    service = ProductsService(DummySession())
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)
    service.variants_repository.get_by_sku = AsyncMock(side_effect=[None, inactive_variant])

    missing = await service.resolve_public_product(
        product_slug=product.slug,
        sku="00002",
        track_view=False,
    )
    inactive = await service.resolve_public_product(
        product_slug=product.slug,
        sku=inactive_variant.sku,
        track_view=False,
    )

    assert missing.route_context.variant_status == "sku_not_found"
    assert missing.route_context.selected_variant_id is None
    assert inactive.route_context.variant_status == "inactive"
    assert inactive.route_context.selected_variant_id is None
    assert [variant.sku for variant in inactive.product.variants] == ["00001"]


@pytest.mark.asyncio
async def test_public_product_resolver_tracks_product_view_when_enabled() -> None:
    tracker = FakeAnalyticsTracker()
    product = _product(status=ProductStatus.ACTIVE)
    service = ProductsService(DummySession(), analytics_tracker=tracker)
    service.repository.get_public_detail_by_slug = AsyncMock(return_value=product)

    await service.resolve_public_product(product_slug=product.slug, user_id=42)

    assert tracker.events == [
        ("product.viewed", {"user_id": 42, "product_id": product.id})
    ]


@pytest.mark.asyncio
async def test_product_service_rejects_multiple_primary_images() -> None:
    service = ProductsService(DummySession())
    service.categories_repository.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(AppError, match="primary"):
        await service.create_product(
            ProductCreate(
                name="Hoodie",
                slug="hoodie",
                base_price=Decimal("59.90"),
                images=[
                    ProductImageCreate(file_path="products/one.jpg", is_primary=True),
                    ProductImageCreate(file_path="products/two.jpg", is_primary=True),
                ],
            )
        )


@pytest.mark.asyncio
async def test_product_variant_service_crud_flow() -> None:
    variant = _variant(stock_quantity=8, reserved_quantity=2)
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=_product())
    service.variants_repository.add = lambda created: setattr(created, "id", 1)
    service.variants_repository.get_by_id = AsyncMock(return_value=variant)
    service.variants_repository.delete = AsyncMock()

    created = await service.create_product_variant(
        1,
        ProductVariantCreate(
            size="M",
            color="Black",
            sku="HOODIE-M-BLK",
            stock_quantity=8,
            reserved_quantity=2,
        ),
    )
    updated = await service.update_product_variant(1, ProductVariantUpdate(stock_quantity=10))
    await service.delete_product_variant(1)

    assert created.id == 1
    assert updated.stock_quantity == 10
    assert updated.available_quantity == 8
    service.variants_repository.delete.assert_awaited_once_with(variant)


@pytest.mark.parametrize("size", CLOTHING_ALPHA_SIZES)
def test_clothing_size_grid_accepts_all_mvp_sizes(size: str) -> None:
    assert normalize_size(ProductSizeGrid.CLOTHING_ALPHA, f" {size.lower()} ") == size


@pytest.mark.parametrize("size", SHOES_EU_SIZES)
def test_shoes_eu_size_grid_accepts_all_mvp_sizes(size: str) -> None:
    assert normalize_size(ProductSizeGrid.SHOES_EU, f" {size} ") == size


@pytest.mark.parametrize("size", SHOES_RU_SIZES)
def test_legacy_shoes_ru_size_grid_accepts_existing_snapshot_sizes(size: str) -> None:
    assert normalize_size(ProductSizeGrid.SHOES_RU, f" {size} ") == size


@pytest.mark.parametrize(
    "size",
    ["M", "XL", "ONE_SIZE", "34", "47", "39.0", "39,5", "RU 39", "EU 39"],
)
def test_shoes_eu_size_grid_rejects_invalid_values(size: str) -> None:
    with pytest.raises(SizeGridValidationError):
        normalize_size(ProductSizeGrid.SHOES_EU, size)


@pytest.mark.parametrize("size", ["42", "XXXL", "XX", "39.0"])
def test_clothing_size_grid_rejects_invalid_values(size: str) -> None:
    with pytest.raises(SizeGridValidationError):
        normalize_size(ProductSizeGrid.CLOTHING_ALPHA, size)


@pytest.mark.asyncio
async def test_product_grid_switch_allows_zero_or_compatible_variants() -> None:
    for variants in ([], [_variant(size="42")]):
        product = _product(variants=variants)
        service = ProductsService(DummySession())
        service.repository.get_by_id = AsyncMock(return_value=product)

        updated = await service.update_product(
            product.id,
            ProductUpdate(size_grid=ProductSizeGrid.SHOES_EU),
        )

        assert updated.size_grid == ProductSizeGrid.SHOES_EU


@pytest.mark.asyncio
async def test_product_create_rejects_legacy_ru_footwear_grid() -> None:
    service = ProductsService(DummySession())

    with pytest.raises(AppError, match="shoes_ru is legacy"):
        await service.create_product(
            ProductCreate(
                name="Legacy Shoes",
                slug="legacy-shoes",
                base_price=Decimal("99.00"),
                size_grid=ProductSizeGrid.SHOES_RU,
            )
        )


@pytest.mark.asyncio
async def test_product_grid_switch_blocks_legacy_ru_to_eu_with_variants() -> None:
    product = _product(
        size_grid=ProductSizeGrid.SHOES_RU,
        variants=[_variant(size="39")],
    )
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)

    with pytest.raises(AppError, match="legacy shoes_ru and shoes_eu"):
        await service.update_product(
            product.id,
            ProductUpdate(size_grid=ProductSizeGrid.SHOES_EU),
        )


@pytest.mark.asyncio
async def test_product_grid_switch_rejects_incompatible_inactive_variants() -> None:
    product = _product(variants=[_variant(size="M", is_active=False)])
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)

    with pytest.raises(AppError, match="incompatible variant sizes: M"):
        await service.update_product(
            product.id,
            ProductUpdate(size_grid=ProductSizeGrid.SHOES_EU),
        )


@pytest.mark.asyncio
async def test_variant_size_is_normalized_against_product_grid() -> None:
    product = _product()
    variant = _variant(size="XL")
    created_variants: list[ProductVariant] = []
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.variants_repository.add = lambda created: (
        setattr(created, "id", 1),
        created_variants.append(created),
    )
    service.variants_repository.get_by_id = AsyncMock(return_value=variant)

    await service.create_product_variant(
        product.id,
        ProductVariantCreate(size=" xl ", sku="HOODIE-XL", stock_quantity=1),
    )

    assert created_variants[0].size == "XL"


@pytest.mark.asyncio
async def test_generate_variant_skus_starts_at_first_numeric_value() -> None:
    service = ProductsService(DummySession())
    service.variants_repository.list_skus = AsyncMock(return_value=[])

    result = await service.generate_variant_skus(1)

    assert result.items == ["00001"]


@pytest.mark.asyncio
async def test_generate_variant_skus_skips_existing_numeric_and_legacy_values() -> None:
    service = ProductsService(DummySession())
    service.variants_repository.list_skus = AsyncMock(
        return_value=["00001", "00003", "tshirt-white-m", "123", "00000"]
    )

    result = await service.generate_variant_skus(3)

    assert result.items == ["00002", "00004", "00005"]


@pytest.mark.asyncio
async def test_generate_variant_skus_reports_exhaustion() -> None:
    service = ProductsService(DummySession())
    service.variants_repository.list_skus = AsyncMock(
        return_value=[f"{value:05d}" for value in range(1, 100000)]
    )

    with pytest.raises(AppError, match="00001-99999 is exhausted"):
        await service.generate_variant_skus(1)


@pytest.mark.asyncio
async def test_generate_product_slugs_starts_at_first_numeric_value() -> None:
    service = ProductsService(DummySession())
    service.repository.list_numeric_slug_candidates = AsyncMock(return_value=[])

    result = await service.generate_product_slugs(1)

    assert result.items == ["00001"]


@pytest.mark.asyncio
async def test_generate_product_slugs_skips_existing_numeric_and_legacy_values() -> None:
    service = ProductsService(DummySession())
    service.repository.list_numeric_slug_candidates = AsyncMock(
        return_value=["00001", "00003", "product-slug", "123", "00000"]
    )

    result = await service.generate_product_slugs(3)

    assert result.items == ["00002", "00004", "00005"]


@pytest.mark.asyncio
async def test_generate_product_slugs_preserves_leading_zeroes() -> None:
    service = ProductsService(DummySession())
    service.repository.list_numeric_slug_candidates = AsyncMock(
        return_value=[f"{value:05d}" for value in range(1, 42)]
    )

    result = await service.generate_product_slugs(1)

    assert result.items == ["00042"]


@pytest.mark.asyncio
async def test_generate_product_slugs_reports_exhaustion() -> None:
    service = ProductsService(DummySession())
    service.repository.list_numeric_slug_candidates = AsyncMock(
        return_value=[f"{value:05d}" for value in range(1, 100000)]
    )

    with pytest.raises(AppError, match="Numeric product slug range 00001-99999 is exhausted"):
        await service.generate_product_slugs(1)


@pytest.mark.asyncio
async def test_product_create_without_slug_generates_numeric_slug() -> None:
    captured: dict[str, Product] = {}
    service = ProductsService(DummySession())
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.list_numeric_slug_candidates = AsyncMock(return_value=[])
    service.repository.add = lambda product: (
        setattr(product, "id", 1),
        captured.setdefault("product", product),
    )
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    created = await service.create_product(
        ProductCreate(name="Hoodie", base_price=Decimal("59.90"))
    )

    assert created.slug == "00001"


@pytest.mark.asyncio
async def test_product_create_with_blank_slug_generates_numeric_slug() -> None:
    captured: dict[str, Product] = {}
    service = ProductsService(DummySession())
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.list_numeric_slug_candidates = AsyncMock(return_value=["00001"])
    service.repository.add = lambda product: (
        setattr(product, "id", 1),
        captured.setdefault("product", product),
    )
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    created = await service.create_product(
        ProductCreate(name="Hoodie", slug="   ", base_price=Decimal("59.90"))
    )

    assert created.slug == "00002"


@pytest.mark.asyncio
async def test_product_create_with_manual_slug_preserves_manual_value() -> None:
    captured: dict[str, Product] = {}
    service = ProductsService(DummySession())
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.list_numeric_slug_candidates = AsyncMock(return_value=["00001"])
    service.repository.add = lambda product: (
        setattr(product, "id", 1),
        captured.setdefault("product", product),
    )
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    created = await service.create_product(
        ProductCreate(name="Hoodie", slug="product-slug", base_price=Decimal("59.90"))
    )

    assert created.slug == "product-slug"
    service.repository.list_numeric_slug_candidates.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_create_duplicate_slug_keeps_conflict_response() -> None:
    service = ProductsService(IntegrityErrorFlushSession())
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.add = lambda _: None

    with pytest.raises(AppError, match="Product slug or variant SKU already exists") as error:
        await service.create_product(
            ProductCreate(name="Hoodie", slug="product-slug", base_price=Decimal("59.90"))
        )

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_variant_create_generates_sku_when_missing() -> None:
    product = _product()
    variant = _variant(size="M", sku="00001")
    created_variants: list[ProductVariant] = []
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.variants_repository.list_skus = AsyncMock(return_value=[])
    service.variants_repository.add = lambda created: (
        setattr(created, "id", 1),
        created_variants.append(created),
    )
    service.variants_repository.get_by_id = AsyncMock(return_value=variant)

    await service.create_product_variant(
        product.id,
        ProductVariantCreate(size="M", stock_quantity=1),
    )

    assert created_variants[0].sku == "00001"


@pytest.mark.asyncio
async def test_variant_create_reallocates_duplicate_generated_sku() -> None:
    product = _product()
    variant = _variant(size="M", sku="00002")
    created_variants: list[ProductVariant] = []
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.variants_repository.list_skus = AsyncMock(return_value=["00001"])
    service.variants_repository.add = lambda created: (
        setattr(created, "id", 1),
        created_variants.append(created),
    )
    service.variants_repository.get_by_id = AsyncMock(return_value=variant)

    await service.create_product_variant(
        product.id,
        ProductVariantCreate(size="M", sku="00001", stock_quantity=1),
    )

    assert created_variants[0].sku == "00002"


@pytest.mark.asyncio
async def test_variant_service_rejects_size_outside_product_grid() -> None:
    product = _product(size_grid=ProductSizeGrid.SHOES_EU)
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)

    with pytest.raises(AppError, match="not valid for shoes_eu"):
        await service.create_product_variant(
            product.id,
            ProductVariantCreate(size="M", sku="SHOE-M", stock_quantity=1),
        )


@pytest.mark.asyncio
async def test_product_update_records_audit_log() -> None:
    audit_service = FakeAuditService()
    product = _product(status=ProductStatus.DRAFT)
    service = ProductsService(DummySession(), audit_service=audit_service)
    service.repository.get_by_id = AsyncMock(return_value=product)

    await service.update_product(
        1,
        ProductUpdate(status=ProductStatus.ACTIVE),
        actor_user_id=2,
    )

    assert audit_service.logs[0]["actor_user_id"] == 2
    assert audit_service.logs[0]["action"] == "product.updated"
    assert audit_service.logs[0]["entity_type"] == "product"
    assert audit_service.logs[0]["entity_id"] == 1


@pytest.mark.asyncio
async def test_product_update_rejects_old_price_below_new_base_price() -> None:
    product = _product(old_price=Decimal("69.90"))
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)

    with pytest.raises(AppError, match="old_price"):
        await service.update_product(1, ProductUpdate(base_price=Decimal("79.90")))


@pytest.mark.asyncio
async def test_product_variant_service_rejects_reserved_quantity_above_stock() -> None:
    service = ProductsService(DummySession())
    service.variants_repository.get_by_id = AsyncMock(
        return_value=_variant(stock_quantity=3, reserved_quantity=1)
    )

    with pytest.raises(AppError, match="reserved_quantity cannot exceed stock_quantity"):
        await service.update_product_variant(1, ProductVariantUpdate(reserved_quantity=4))


def test_inventory_available_quantity_calculation() -> None:
    assert calculate_available_quantity(stock_quantity=7, reserved_quantity=2) == 5


def test_product_availability_requires_active_variant_with_available_stock() -> None:
    product = _product(
        status=ProductStatus.ACTIVE,
        variants=[
            _variant(stock_quantity=5, reserved_quantity=5, is_active=True),
            _variant(stock_quantity=3, reserved_quantity=0, is_active=False),
        ],
    )
    assert product.is_available is False

    product.variants.append(_variant(stock_quantity=1, reserved_quantity=0, is_active=True))
    assert product.is_available is True


def test_product_create_defaults_search_priority_to_medium() -> None:
    product = ProductCreate(name="Hoodie", slug="hoodie", base_price=Decimal("59.90"))

    assert product.search_priority == SEARCH_PRIORITY_DEFAULT == 2
    assert product.size_grid == ProductSizeGrid.CLOTHING_ALPHA
    assert product.image_badge_type == ProductImageBadgeType.NONE
    assert product.image_badge_text is None
    assert product.image_badge_color is None
    assert product.image_badge_position is None


def test_product_create_accepts_configurable_badge_appearance() -> None:
    product = ProductCreate(
        name="Hoodie",
        slug="hoodie",
        base_price=Decimal("59.90"),
        image_badge_type=ProductImageBadgeType.HIT,
        image_badge_color=ProductImageBadgeColor.GREEN,
        image_badge_position=ProductImageBadgePosition.BOTTOM_RIGHT,
    )

    assert product.image_badge_color == ProductImageBadgeColor.GREEN
    assert product.image_badge_position == ProductImageBadgePosition.BOTTOM_RIGHT


def test_product_create_rejects_invalid_badge_appearance_values() -> None:
    with pytest.raises(ValidationError) as color_error:
        ProductCreate(
            name="Hoodie",
            slug="hoodie",
            base_price=Decimal("59.90"),
            image_badge_color="teal",
        )

    with pytest.raises(ValidationError) as position_error:
        ProductCreate(
            name="Hoodie",
            slug="hoodie",
            base_price=Decimal("59.90"),
            image_badge_position="center",
        )

    assert "image_badge_color" in str(color_error.value)
    assert "image_badge_position" in str(position_error.value)


def test_product_brand_is_optional_and_normalized() -> None:
    product = ProductCreate(
        name="Hoodie",
        slug="hoodie",
        brand="  ICON STORE  ",
        base_price=Decimal("59.90"),
    )
    update = ProductUpdate(brand="  ")

    assert product.brand == "ICON STORE"
    assert update.brand is None


def test_product_create_rejects_duplicate_related_product_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate related product"):
        ProductCreate(
            name="Hoodie",
            slug="hoodie",
            base_price=Decimal("59.90"),
            related_product_ids=[2, 2],
        )


def test_product_custom_badge_requires_safe_bounded_text() -> None:
    with pytest.raises(ValidationError, match="required for a custom badge"):
        ProductCreate(
            name="Hoodie",
            slug="hoodie",
            base_price=Decimal("59.90"),
            image_badge_type=ProductImageBadgeType.CUSTOM,
        )

    with pytest.raises(ValidationError, match="must not contain HTML"):
        ProductCreate(
            name="Hoodie",
            slug="hoodie-html",
            base_price=Decimal("59.90"),
            image_badge_type=ProductImageBadgeType.CUSTOM,
            image_badge_text="<b>HOT</b>",
        )


@pytest.mark.asyncio
async def test_product_update_rejects_unknown_related_product_ids() -> None:
    product = _product()
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.repository.list_existing_ids = AsyncMock(return_value={2})

    with pytest.raises(AppError, match="Unknown related product IDs: 999") as error:
        await service.update_product(
            product.id,
            ProductUpdate(related_product_ids=[2, 999]),
        )

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_product_create_rejects_unknown_related_product_ids() -> None:
    session = DummySession()
    added_products: list[Product] = []
    service = ProductsService(session)
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.list_existing_ids = AsyncMock(return_value=set())
    service.repository.add = added_products.append

    with pytest.raises(AppError, match="Unknown related product IDs: 999") as error:
        await service.create_product(
            ProductCreate(
                name="Hoodie",
                slug="hoodie-related",
                base_price=Decimal("59.90"),
                related_product_ids=[999],
            )
        )

    assert error.value.status_code == 400
    assert added_products == []
    assert session.flush_count == 0
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_product_create_rejects_self_related_product_after_id_assignment() -> None:
    captured: dict[str, Product] = {}
    session = InspectingFirstFlushSession(captured, assigned_id=2)
    service = ProductsService(session)
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.list_existing_ids = AsyncMock(return_value={2})
    service.repository.add = lambda product: captured.setdefault("product", product)

    with pytest.raises(AppError, match="cannot be related to itself") as error:
        await service.create_product(
            ProductCreate(
                name="Hoodie",
                slug="hoodie-related",
                base_price=Decimal("59.90"),
                related_product_ids=[2],
            )
        )

    assert error.value.status_code == 400
    assert session.flush_count == 1
    assert session.committed is False
    assert session.rollback_count == 1


@pytest.mark.asyncio
async def test_product_create_with_empty_related_products_initializes_links_before_flush() -> None:
    captured: dict[str, Product] = {}
    session = InspectingFirstFlushSession(captured)
    service = ProductsService(session)
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.list_existing_ids = AsyncMock(return_value=set())
    service.repository.add = lambda product: captured.setdefault("product", product)
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    created = await service.create_product(
        ProductCreate(
            name="Hoodie",
            slug="hoodie-empty-related",
            base_price=Decimal("59.90"),
            related_product_ids=[],
        )
    )

    assert created.id == 10
    assert created.related_product_ids == []
    assert created.related_product_links == []
    assert session.flush_count == 2
    service.repository.list_existing_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_create_persists_single_related_product_position() -> None:
    captured: dict[str, Product] = {}
    service = ProductsService(InspectingFirstFlushSession(captured))
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.list_existing_ids = AsyncMock(return_value={2})
    service.repository.add = lambda product: captured.setdefault("product", product)
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    created = await service.create_product(
        ProductCreate(
            name="Hoodie",
            slug="hoodie-related-single",
            base_price=Decimal("59.90"),
            related_product_ids=[2],
        )
    )

    assert created.related_product_ids == [2]
    assert [
        (link.related_product_id, link.position)
        for link in created.related_product_links
    ] == [(2, 0)]
    service.repository.list_existing_ids.assert_awaited_once_with([2])


@pytest.mark.asyncio
async def test_product_create_persists_related_product_order() -> None:
    captured: dict[str, Product] = {}
    session = InspectingFirstFlushSession(captured)
    service = ProductsService(session)
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])
    service.repository.list_existing_ids = AsyncMock(return_value={2, 3})

    def capture_product(product: Product) -> None:
        captured["product"] = product

    service.repository.add = capture_product
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    created = await service.create_product(
        ProductCreate(
            name="Hoodie",
            slug="hoodie-related",
            base_price=Decimal("59.90"),
            related_product_ids=[3, 2],
        )
    )

    assert created.related_product_ids == [3, 2]
    assert [
        (link.related_product_id, link.position)
        for link in created.related_product_links
    ] == [(3, 0), (2, 1)]
    assert session.flush_count == 2


@pytest.mark.asyncio
async def test_product_create_accepts_full_seller_panel_payload() -> None:
    captured: dict[str, Product] = {}
    service = ProductsService(InspectingFirstFlushSession(captured))
    service.categories_repository.get_by_id = AsyncMock(return_value=_category())
    service.tags_repository.list_by_ids = AsyncMock(
        return_value=[_tag(), _tag(tag_id=2, name="Winter", slug="winter")]
    )
    service.repository.list_existing_ids = AsyncMock(return_value=set())
    service.repository.add = lambda product: captured.setdefault("product", product)
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    product = await service.create_product(
        ProductCreate(
            name="Seller Panel Coat",
            slug="seller-panel-coat",
            brand="ICON STORE",
            description="Warm dashboard-created item",
            base_price=Decimal("129.90"),
            old_price=Decimal("159.90"),
            search_priority=1,
            search_aliases="winter coat, coat",
            image_badge_type=ProductImageBadgeType.CUSTOM,
            image_badge_text=" New ",
            image_badge_color=ProductImageBadgeColor.PINK,
            image_badge_position=ProductImageBadgePosition.TOP_RIGHT,
            status=ProductStatus.ACTIVE,
            categories=[
                {"category_id": 1, "priority": 1},
                {"category_id": 2, "priority": 2},
            ],
            tag_ids=[1, 2],
            images=[],
            related_product_ids=[],
        )
    )

    assert product.category_id == 1
    assert [
        (assignment.category_id, assignment.priority)
        for assignment in product.product_categories
    ] == [(1, 1), (2, 2)]
    assert [tag.id for tag in product.tags] == [1, 2]
    assert product.image_badge_type == ProductImageBadgeType.CUSTOM
    assert product.image_badge_text == "New"
    assert product.image_badge_color == ProductImageBadgeColor.PINK
    assert product.image_badge_position == ProductImageBadgePosition.TOP_RIGHT
    assert product.search_priority == 1
    assert product.search_aliases == "winter coat\ncoat"
    assert product.images == []
    assert product.related_product_links == []
    assert product.status == ProductStatus.ACTIVE
    service.repository.list_existing_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_update_rejects_self_related_product() -> None:
    product = _product()
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)

    with pytest.raises(AppError, match="cannot be related to itself") as error:
        await service.update_product(
            product.id,
            ProductUpdate(related_product_ids=[product.id]),
        )

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_product_update_persists_related_product_order_and_badge() -> None:
    product = _product()
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.repository.list_existing_ids = AsyncMock(return_value={2, 3})

    updated = await service.update_product(
        product.id,
        ProductUpdate(
            related_product_ids=[3, 2],
            image_badge_type=ProductImageBadgeType.CUSTOM,
            image_badge_text=" Только сегодня ",
            image_badge_color=ProductImageBadgeColor.PINK,
            image_badge_position=ProductImageBadgePosition.TOP_RIGHT,
        ),
    )

    assert updated.related_product_ids == [3, 2]
    assert updated.image_badge_type == ProductImageBadgeType.CUSTOM
    assert updated.image_badge_text == "Только сегодня"
    assert updated.image_badge_color == ProductImageBadgeColor.PINK
    assert updated.image_badge_position == ProductImageBadgePosition.TOP_RIGHT


def test_old_product_without_badge_appearance_serializes() -> None:
    product = ProductRead.model_validate(_product())

    assert product.image_badge_color is None
    assert product.image_badge_position is None


def test_product_create_rejects_old_price_not_above_base_price() -> None:
    with pytest.raises(ValidationError, match="old_price"):
        ProductCreate(
            name="Hoodie",
            slug="hoodie",
            base_price=Decimal("59.90"),
            old_price=Decimal("49.90"),
        )


def test_product_create_rejects_more_than_three_categories() -> None:
    with pytest.raises(ValidationError, match="at most 3 categories"):
        ProductCreate(
            name="Suit",
            slug="suit",
            base_price=Decimal("199.90"),
            categories=[
                {"category_id": 1, "priority": 1},
                {"category_id": 2, "priority": 2},
                {"category_id": 3, "priority": 3},
                {"category_id": 4, "priority": 1},
            ],
        )


def test_product_create_rejects_duplicate_category_assignment() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        ProductCreate(
            name="Suit",
            slug="suit",
            base_price=Decimal("199.90"),
            categories=[
                {"category_id": 1, "priority": 1},
                {"category_id": 1, "priority": 2},
            ],
        )


def test_product_create_rejects_duplicate_category_priority() -> None:
    with pytest.raises(ValidationError, match="priorities"):
        ProductCreate(
            name="Suit",
            slug="suit",
            base_price=Decimal("199.90"),
            categories=[
                {"category_id": 1, "priority": 1},
                {"category_id": 2, "priority": 1},
            ],
        )


@pytest.mark.asyncio
async def test_product_service_sets_prioritized_categories_and_primary_category() -> None:
    captured: dict[str, Product] = {}
    service = ProductsService(DummySession())
    service.categories_repository.get_by_id = AsyncMock(return_value=_category())
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])

    def capture_product(product: Product) -> None:
        product.id = 1
        captured["product"] = product

    service.repository.add = capture_product
    service.repository.get_by_id = AsyncMock(side_effect=lambda _: captured["product"])

    product = await service.create_product(
        ProductCreate(
            name="Suit",
            slug="suit",
            base_price=Decimal("199.90"),
            categories=[
                {"category_id": 2, "priority": 2},
                {"category_id": 1, "priority": 1},
                {"category_id": 3, "priority": 3},
            ],
        )
    )

    assert product.category_id == 1
    assert [
        (assignment.category_id, assignment.priority)
        for assignment in product.product_categories
    ] == [(1, 1), (2, 2), (3, 3)]


@pytest.mark.asyncio
async def test_product_update_can_set_prioritized_categories() -> None:
    product = _product()
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.categories_repository.get_by_id = AsyncMock(return_value=_category())

    updated = await service.update_product(
        1,
        ProductUpdate(
            categories=[
                {"category_id": 3, "priority": 3},
                {"category_id": 2, "priority": 1},
            ]
        ),
    )

    assert updated.category_id == 2
    assert [
        (assignment.category_id, assignment.priority)
        for assignment in updated.product_categories
    ] == [(2, 1), (3, 3)]


@pytest.mark.asyncio
async def test_product_update_adds_tags_without_rewriting_existing_categories() -> None:
    product = _product(size_grid=ProductSizeGrid.SHOES_RU)
    original_categories = list(product.product_categories)
    session = DummySession()
    service = ProductsService(session)
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.categories_repository.get_by_id = AsyncMock(return_value=_category())
    service.tags_repository.list_by_ids = AsyncMock(
        return_value=[_tag(), _tag(tag_id=2, name="Footwear", slug="footwear")]
    )

    updated = await service.update_product(
        1,
        ProductUpdate(
            category_id=1,
            categories=[{"category_id": 1, "priority": 1}],
            size_grid=ProductSizeGrid.SHOES_RU,
            tag_ids=[1, 2],
        ),
    )

    assert [tag.id for tag in updated.tags] == [1, 2]
    assert updated.product_categories == original_categories
    assert session.flush_count == 1


@pytest.mark.asyncio
async def test_product_update_removes_tags() -> None:
    product = _product()
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])

    updated = await service.update_product(1, ProductUpdate(tag_ids=[]))

    assert updated.tags == []


@pytest.mark.asyncio
async def test_product_update_rejects_unknown_tag_id_as_bad_request() -> None:
    product = _product()
    session = DummySession()
    service = ProductsService(session)
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.tags_repository.list_by_ids = AsyncMock(return_value=[])

    with pytest.raises(AppError, match="Unknown tag_ids: 999") as error:
        await service.update_product(1, ProductUpdate(tag_ids=[999]))

    assert error.value.status_code == 400
    assert session.committed is False


def test_product_search_aliases_are_normalized() -> None:
    assert normalize_search_aliases(" футболки, футболка\nфутболки ") == "футболки\nфутболка"


def test_typo_tolerant_search_matches_required_russian_queries() -> None:
    haystack = "Футболки хлопковые oversize"

    assert search_text_matches_query(haystack, "футболка")
    assert search_text_matches_query(haystack, "футблоки")
    assert search_text_matches_query(haystack, "фудболка")
    assert search_text_matches_query(haystack, "фтболка")


@pytest.mark.parametrize("query", ["белый", "белая", "блеый", "белий"])
def test_russian_white_color_queries_expand_to_latin(query: str) -> None:
    assert "white" in expand_color_query(query)
    assert "белый" in expand_color_query(query)


@pytest.mark.parametrize("query", ["черный", "чёрный"])
def test_russian_black_color_queries_expand_to_latin(query: str) -> None:
    expanded = expand_color_query(query)
    assert "black" in expanded
    assert "черный" in expanded


def test_latin_color_queries_expand_to_russian_aliases() -> None:
    expanded = expand_color_query("black")

    assert "black" in expanded
    assert "черный" in expanded


def test_general_search_matches_active_variant_color_and_multiword_query() -> None:
    repository = ProductsRepository(DummySession())

    white_sql = _literal_sql(repository._search_condition("White"))
    russian_sql = _literal_sql(repository._search_condition("футболка белая"))

    assert "product_variants.color" in white_sql
    assert "product_variants.is_active IS true" in white_sql
    assert "white" in russian_sql
    assert "футболка" in russian_sql


def test_numeric_search_matches_active_variant_size_exactly() -> None:
    repository = ProductsRepository(DummySession())

    rendered = _literal_sql(repository._search_condition("42"))

    assert "product_variants.size = '42'" in rendered
    assert "142" not in rendered
    assert "product_variants.is_active IS true" in rendered


def test_size_and_color_filters_use_the_same_active_variant() -> None:
    repository = ProductsRepository(DummySession())
    filters = repository._build_filters(
        category_id=None,
        tag_id=None,
        status=ProductStatus.ACTIVE,
        search=None,
        size_grid=ProductSizeGrid.SHOES_EU,
        size="42",
        color="белая",
    )

    rendered = _literal_sql(filters[-1])
    assert rendered.count("EXISTS") == 1
    assert "product_variants.size = '42'" in rendered
    assert "white" in rendered
    assert "белый" in rendered
    assert "product_variants.is_active IS true" in rendered


def test_color_filter_keeps_latin_and_russian_variant_colors_searchable() -> None:
    repository = ProductsRepository(DummySession())
    filters = repository._build_filters(
        category_id=None,
        tag_id=None,
        status=ProductStatus.ACTIVE,
        search=None,
        color="black",
    )

    rendered = _literal_sql(filters[-1])
    assert "black" in rendered
    assert "черный" in rendered
    assert "product_variants.color" in rendered


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"category_id": 1},
        {"tag_id": 1},
        {"search": "hoodie"},
    ],
)
async def test_public_product_card_queries_require_listed_products(
    filters: dict[str, object],
) -> None:
    session = CapturingQuerySession()
    repository = ProductsRepository(session)  # type: ignore[arg-type]

    await repository.list_public_cards(limit=20, offset=0, **filters)

    rendered = "\n".join(_literal_sql(statement) for statement in session.statements)
    assert "products.is_listed IS true" in rendered


@pytest.mark.asyncio
async def test_admin_product_list_does_not_filter_unlisted_products() -> None:
    session = CapturingQuerySession()
    repository = ProductsRepository(session)  # type: ignore[arg-type]

    await repository.list(limit=20, offset=0, status=ProductStatus.ACTIVE)

    rendered = "\n".join(_literal_sql(statement) for statement in session.statements)
    assert "products.is_listed IS true" not in rendered


@pytest.mark.asyncio
async def test_public_search_suggestions_require_listed_products() -> None:
    session = CapturingQuerySession()
    repository = ProductsRepository(session)  # type: ignore[arg-type]

    await repository.list_search_suggestions(query="hoodie", limit=8)

    rendered = "\n".join(_literal_sql(statement) for statement in session.statements)
    assert rendered.count("products.is_listed IS true") >= 5


def test_product_variant_color_is_stored_as_trimmed_display_text() -> None:
    variant = ProductVariantCreate(size="M", color="  Красный  ", sku="RED-M")
    update = ProductVariantUpdate(color="  ")

    assert variant.color == "Красный"
    assert update.color is None


def test_repository_search_ordering_prioritizes_lower_numeric_priority() -> None:
    repository = ProductsRepository(DummySession())
    ordering = repository._list_ordering(search="футболка")

    assert "search_priority" in str(ordering[0])
    assert "created_at" in str(ordering[1])


def test_repository_category_filter_uses_assignment_relation() -> None:
    repository = ProductsRepository(DummySession())
    filters = repository._build_filters(
        category_id=2,
        tag_id=None,
        status=ProductStatus.ACTIVE,
        search=None,
    )

    rendered = " ".join(str(item) for item in filters)
    assert "product_categories" in rendered


def test_repository_category_context_orders_by_category_priority() -> None:
    repository = ProductsRepository(DummySession())
    ordering = repository._list_ordering(search=None, category_id=2)

    assert "product_categories.priority" in str(ordering[0])


def _category(
    *,
    category_id: int = 1,
    name: str = "Hoodies",
    slug: str = "hoodies",
    image_path: str | None = None,
) -> Category:
    return Category(
        id=category_id,
        name=name,
        slug=slug,
        description=None,
        image_path=image_path,
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )


def _tag(
    *,
    tag_id: int = 1,
    name: str = "Premium",
    slug: str = "premium",
    image_path: str | None = None,
) -> Tag:
    return Tag(
        id=tag_id,
        name=name,
        slug=slug,
        image_path=image_path,
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )


def _product(
    product_id: int = 1,
    status: ProductStatus = ProductStatus.DRAFT,
    variants: list[ProductVariant] | None = None,
    old_price: Decimal | None = None,
    size_grid: ProductSizeGrid = ProductSizeGrid.CLOTHING_ALPHA,
    is_listed: bool = True,
    is_returnable: bool = True,
) -> Product:
    return Product(
        id=product_id,
        name="Hoodie",
        slug="hoodie",
        description="Warm",
        base_price=Decimal("59.90"),
        old_price=old_price,
        search_priority=SEARCH_PRIORITY_DEFAULT,
        search_aliases=None,
        size_grid=size_grid,
        image_badge_type=ProductImageBadgeType.NONE,
        image_badge_text=None,
        image_badge_color=None,
        image_badge_position=None,
        status=status,
        is_listed=is_listed,
        is_returnable=is_returnable,
        category_id=1,
        category=_category(),
        product_categories=[
            ProductCategory(category_id=1, priority=1, category=_category()),
        ],
        tags=[_tag()],
        images=[],
        variants=variants or [],
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )


def _variant(
    *,
    stock_quantity: int = 5,
    reserved_quantity: int = 0,
    is_active: bool = True,
    size: str = "M",
    sku: str = "HOODIE-M-BLK",
) -> ProductVariant:
    return ProductVariant(
        id=1,
        product_id=1,
        size=size,
        color="Black",
        sku=sku,
        stock_quantity=stock_quantity,
        reserved_quantity=reserved_quantity,
        is_active=is_active,
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )


def _literal_sql(expression: object) -> str:
    return str(
        expression.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
