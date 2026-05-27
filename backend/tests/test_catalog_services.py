from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import Category, Product, ProductStatus, Tag
from app.modules.categories.schemas import CategoryCreate, CategoryUpdate
from app.modules.categories.service import CategoriesService
from app.modules.products.schemas import (
    ProductCreate,
    ProductImageCreate,
    ProductList,
    ProductUpdate,
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


def _product(status: ProductStatus = ProductStatus.DRAFT) -> Product:
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
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )
