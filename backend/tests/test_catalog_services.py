from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import Category, Product, ProductStatus, ProductVariant, Tag
from app.modules.categories.schemas import CategoryCreate, CategoryUpdate
from app.modules.categories.service import CategoriesService
from app.modules.products.inventory import calculate_available_quantity
from app.modules.products.schemas import (
    ProductCreate,
    ProductImageCreate,
    ProductList,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)
from app.modules.products.service import ProductsService
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
        active_variants_only=True,
    )


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
) -> Product:
    return Product(
        id=1,
        name="Hoodie",
        slug="hoodie",
        description="Warm",
        base_price=Decimal("59.90"),
        status=status,
        category_id=1,
        category=_category(),
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
) -> ProductVariant:
    return ProductVariant(
        id=1,
        product_id=1,
        size="M",
        color="Black",
        sku="HOODIE-M-BLK",
        stock_quantity=stock_quantity,
        reserved_quantity=reserved_quantity,
        is_active=is_active,
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )
