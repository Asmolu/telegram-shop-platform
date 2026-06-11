from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import (
    Category,
    Product,
    ProductCategory,
    ProductSizeGrid,
    ProductStatus,
    ProductVariant,
    Tag,
)
from app.modules.categories.schemas import CategoryCreate, CategoryUpdate
from app.modules.categories.service import CategoriesService
from app.modules.products.inventory import calculate_available_quantity
from app.modules.products.repository import ProductsRepository
from app.modules.products.schemas import (
    ProductCreate,
    ProductImageCreate,
    ProductList,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.modules.products.search import (
    SEARCH_PRIORITY_DEFAULT,
    expand_color_query,
    normalize_search_aliases,
    search_text_matches_query,
)
from app.modules.products.service import ProductsService
from app.modules.products.size_grids import (
    CLOTHING_ALPHA_SIZES,
    SHOES_RU_SIZES,
    SizeGridValidationError,
    normalize_size,
)
from app.modules.tags.schemas import TagCreate, TagUpdate
from app.modules.tags.service import TagsService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.deleted = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.committed = False

    async def refresh(self, _: object) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def delete(self, _: object) -> None:
        self.deleted = True


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
async def test_public_product_list_never_exposes_non_active_statuses() -> None:
    service = ProductsService(DummySession())
    service.repository.list = AsyncMock(
        return_value=([_product(status=ProductStatus.DRAFT)], 1)
    )

    result = await service.list_public_products(
        limit=20,
        offset=0,
        status=ProductStatus.DRAFT,
    )

    assert result == ProductList(items=[], meta=PageMeta(limit=20, offset=0, total=0))
    service.repository.list.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_product_list_loads_only_active_variants() -> None:
    service = ProductsService(DummySession())
    service.repository.list = AsyncMock(return_value=([_product(status=ProductStatus.ACTIVE)], 1))

    result = await service.list_public_products(limit=20, offset=0)

    assert result.meta.total == 1
    service.repository.list.assert_awaited_once_with(
        limit=20,
        offset=0,
        category_id=None,
        tag_id=None,
        status=ProductStatus.ACTIVE,
        search=None,
        size_grid=None,
        size=None,
        color=None,
        active_variants_only=True,
    )


@pytest.mark.asyncio
async def test_public_product_search_tracks_sanitized_query() -> None:
    tracker = FakeAnalyticsTracker()
    service = ProductsService(DummySession(), analytics_tracker=tracker)
    service.repository.list = AsyncMock(return_value=([], 0))

    await service.list_public_products(limit=20, offset=0, search=" \n футболка \t ")

    assert tracker.events == [
        (
            "search.performed",
            {"user_id": None, "metadata": {"query": "футболка", "result_count": 0}},
        )
    ]


@pytest.mark.asyncio
async def test_public_product_detail_tracks_product_view() -> None:
    tracker = FakeAnalyticsTracker()
    service = ProductsService(DummySession(), analytics_tracker=tracker)
    service.repository.get_active_by_id = AsyncMock(
        return_value=_product(status=ProductStatus.ACTIVE)
    )

    product = await service.get_public_product(1, user_id=None)

    assert product.id == 1
    assert tracker.events == [
        (
            "product.viewed",
            {"user_id": None, "product_id": 1},
        )
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


@pytest.mark.parametrize("size", SHOES_RU_SIZES)
def test_shoes_ru_size_grid_accepts_all_mvp_sizes(size: str) -> None:
    assert normalize_size(ProductSizeGrid.SHOES_RU, f" {size} ") == size


@pytest.mark.parametrize(
    "size",
    ["M", "XL", "ONE_SIZE", "34", "47", "39.0", "39,5", "RU 39", "EU 39"],
)
def test_shoes_ru_size_grid_rejects_invalid_values(size: str) -> None:
    with pytest.raises(SizeGridValidationError):
        normalize_size(ProductSizeGrid.SHOES_RU, size)


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
            ProductUpdate(size_grid=ProductSizeGrid.SHOES_RU),
        )

        assert updated.size_grid == ProductSizeGrid.SHOES_RU


@pytest.mark.asyncio
async def test_product_grid_switch_rejects_incompatible_inactive_variants() -> None:
    product = _product(variants=[_variant(size="M", is_active=False)])
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)

    with pytest.raises(AppError, match="incompatible variant sizes: M"):
        await service.update_product(
            product.id,
            ProductUpdate(size_grid=ProductSizeGrid.SHOES_RU),
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
async def test_variant_service_rejects_size_outside_product_grid() -> None:
    product = _product(size_grid=ProductSizeGrid.SHOES_RU)
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)

    with pytest.raises(AppError, match="not valid for shoes_ru"):
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


@pytest.mark.parametrize("query", ["черный", "чёрный"])
def test_russian_black_color_queries_expand_to_latin(query: str) -> None:
    assert expand_color_query(query) == ("black",)


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
        size_grid=ProductSizeGrid.SHOES_RU,
        size="42",
        color="белая",
    )

    rendered = _literal_sql(filters[-1])
    assert rendered.count("EXISTS") == 1
    assert "product_variants.size = '42'" in rendered
    assert "white" in rendered
    assert "product_variants.is_active IS true" in rendered


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


def _category() -> Category:
    return Category(
        id=1,
        name="Hoodies",
        slug="hoodies",
        description=None,
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )


def _tag() -> Tag:
    return Tag(
        id=1,
        name="Premium",
        slug="premium",
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )


def _product(
    status: ProductStatus = ProductStatus.DRAFT,
    variants: list[ProductVariant] | None = None,
    old_price: Decimal | None = None,
    size_grid: ProductSizeGrid = ProductSizeGrid.CLOTHING_ALPHA,
) -> Product:
    return Product(
        id=1,
        name="Hoodie",
        slug="hoodie",
        description="Warm",
        base_price=Decimal("59.90"),
        old_price=old_price,
        search_priority=SEARCH_PRIORITY_DEFAULT,
        search_aliases=None,
        size_grid=size_grid,
        status=status,
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
) -> ProductVariant:
    return ProductVariant(
        id=1,
        product_id=1,
        size=size,
        color="Black",
        sku="HOODIE-M-BLK",
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
