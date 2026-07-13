from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.errors import AppError
from app.db.models import (
    Category,
    Look,
    LookItem,
    LookStatus,
    Product,
    ProductCategory,
    ProductImageBadgeType,
    ProductSizeGrid,
    ProductSizeGroup,
    ProductStatus,
    ProductVariant,
    RouteAlias,
    RouteAliasEntityType,
)
from app.modules.categories.schemas import CategoryUpdate
from app.modules.categories.service import CategoriesService
from app.modules.looks.schemas import LookUpdate
from app.modules.looks.service import LooksService
from app.modules.products.schemas import ProductUpdate
from app.modules.products.service import ProductsService
from app.modules.route_aliases.service import RouteAliasesService

NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


class DummySession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rollback_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, _instance: object) -> None:
        return None


class InMemoryRouteAliasRepository:
    def __init__(self, aliases: list[RouteAlias] | None = None) -> None:
        self.aliases = aliases or []
        self.next_id = 1
        for route_alias in self.aliases:
            self._persist(route_alias)

    async def get_active_by_slug(
        self,
        entity_type: RouteAliasEntityType,
        alias_slug: str,
    ) -> RouteAlias | None:
        return next(
            (
                route_alias
                for route_alias in self.aliases
                if route_alias.entity_type == entity_type
                and route_alias.alias_slug == alias_slug
                and route_alias.is_active
            ),
            None,
        )

    async def get_active_for_entity_slug(
        self,
        entity_type: RouteAliasEntityType,
        entity_id: int,
        alias_slug: str,
    ) -> RouteAlias | None:
        return next(
            (
                route_alias
                for route_alias in self.aliases
                if route_alias.entity_type == entity_type
                and route_alias.entity_id == entity_id
                and route_alias.alias_slug == alias_slug
                and route_alias.is_active
            ),
            None,
        )

    async def list_active_alias_slugs(self, entity_type: RouteAliasEntityType) -> list[str]:
        return [
            route_alias.alias_slug
            for route_alias in self.aliases
            if route_alias.entity_type == entity_type and route_alias.is_active
        ]

    def add(self, route_alias: RouteAlias) -> None:
        self._persist(route_alias)
        self.aliases.append(route_alias)

    def _persist(self, route_alias: RouteAlias) -> None:
        if getattr(route_alias, "id", None) is None:
            route_alias.id = self.next_id
            self.next_id += 1
        if route_alias.is_active is None:
            route_alias.is_active = True
        route_alias.created_at = getattr(route_alias, "created_at", None) or NOW
        route_alias.updated_at = getattr(route_alias, "updated_at", None) or NOW


class PublicProductRepository:
    def __init__(self, product: Product) -> None:
        self.product = product

    async def get_public_detail_by_slug(self, product_slug: str) -> Product | None:
        if self.product.slug == product_slug and self.product.status == ProductStatus.ACTIVE:
            return self.product
        return None

    async def get_public_detail_by_id(self, product_id: int) -> Product | None:
        if self.product.id == product_id and self.product.status == ProductStatus.ACTIVE:
            return self.product
        return None


class PublicCategoryRepository:
    def __init__(self, category: Category) -> None:
        self.category = category

    async def get_by_slug(self, slug: str) -> Category | None:
        return self.category if self.category.slug == slug else None

    async def get_by_id(self, category_id: int) -> Category | None:
        return self.category if self.category.id == category_id else None


class PublicLookRepository:
    def __init__(self, look: Look) -> None:
        self.look = look

    async def get_public_by_slug(self, slug: str) -> Look | None:
        if self.look.slug == slug and self.look.status == LookStatus.ACTIVE and self.look.is_listed:
            return self.look
        return None

    async def get_public_by_id(self, look_id: int) -> Look | None:
        if (
            self.look.id == look_id
            and self.look.status == LookStatus.ACTIVE
            and self.look.is_listed
        ):
            return self.look
        return None


@pytest.mark.asyncio
async def test_product_slug_update_creates_product_alias_for_old_slug() -> None:
    product = _product(slug="old-product")
    alias_repository = InMemoryRouteAliasRepository()
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.repository.get_by_slug = AsyncMock(return_value=None)
    service.route_aliases = _route_aliases(alias_repository)

    result = await service.update_product(
        product.id,
        ProductUpdate(slug="current-product"),
        actor_user_id=9,
    )

    assert result.slug == "current-product"
    alias = await alias_repository.get_active_by_slug(RouteAliasEntityType.PRODUCT, "old-product")
    assert alias is not None
    assert alias.entity_id == product.id
    assert alias.created_by_user_id == 9


@pytest.mark.asyncio
async def test_category_slug_update_creates_category_alias_for_old_slug() -> None:
    category = _category(slug="old-category")
    alias_repository = InMemoryRouteAliasRepository()
    service = CategoriesService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=category)
    service.repository.get_by_slug = AsyncMock(return_value=None)
    service.route_aliases = _route_aliases(alias_repository)

    result = await service.update_category(
        category.id,
        CategoryUpdate(slug="current-category"),
        actor_user_id=9,
    )

    assert result.slug == "current-category"
    alias = await alias_repository.get_active_by_slug(RouteAliasEntityType.CATEGORY, "old-category")
    assert alias is not None
    assert alias.entity_id == category.id
    assert alias.created_by_user_id == 9


@pytest.mark.asyncio
async def test_look_slug_update_creates_look_alias_for_old_slug() -> None:
    look = _look(slug="old-look")
    alias_repository = InMemoryRouteAliasRepository()
    service = LooksService(DummySession())
    service.repository.get_admin_by_id = AsyncMock(return_value=look)
    service.repository.get_by_slug = AsyncMock(return_value=None)
    service.route_aliases = _route_aliases(alias_repository)

    result = await service.update_admin_look(
        look.id,
        LookUpdate(slug="current-look"),
        actor_user_id=9,
    )

    assert result.slug == "current-look"
    alias = await alias_repository.get_active_by_slug(RouteAliasEntityType.LOOK, "old-look")
    assert alias is not None
    assert alias.entity_id == look.id
    assert alias.created_by_user_id == 9


@pytest.mark.asyncio
async def test_repeated_product_slug_changes_keep_all_old_slugs_resolving() -> None:
    product = _product(slug="first-product")
    alias_repository = InMemoryRouteAliasRepository()
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.repository.get_by_slug = AsyncMock(return_value=None)
    service.route_aliases = _route_aliases(alias_repository)

    await service.update_product(product.id, ProductUpdate(slug="second-product"))
    await service.update_product(product.id, ProductUpdate(slug="third-product"))

    active_aliases = await alias_repository.list_active_alias_slugs(RouteAliasEntityType.PRODUCT)
    assert active_aliases == ["first-product", "second-product"]


@pytest.mark.asyncio
async def test_duplicate_alias_for_same_entity_is_not_created() -> None:
    product = _product(slug="old-product")
    alias_repository = InMemoryRouteAliasRepository(
        [_alias(RouteAliasEntityType.PRODUCT, entity_id=product.id, alias_slug="old-product")]
    )
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.repository.get_by_slug = AsyncMock(return_value=None)
    service.route_aliases = _route_aliases(alias_repository)

    await service.update_product(product.id, ProductUpdate(slug="current-product"))

    active_aliases = await alias_repository.list_active_alias_slugs(RouteAliasEntityType.PRODUCT)
    assert active_aliases == ["old-product"]


@pytest.mark.asyncio
async def test_new_slug_conflicting_with_another_active_alias_is_rejected() -> None:
    product = _product(product_id=1, slug="old-product")
    alias_repository = InMemoryRouteAliasRepository(
        [_alias(RouteAliasEntityType.PRODUCT, entity_id=2, alias_slug="taken-slug")]
    )
    service = ProductsService(DummySession())
    service.repository.get_by_id = AsyncMock(return_value=product)
    service.repository.get_by_slug = AsyncMock(return_value=None)
    service.route_aliases = _route_aliases(alias_repository)

    with pytest.raises(AppError, match="active route alias") as exc_info:
        await service.update_product(product.id, ProductUpdate(slug="taken-slug"))

    assert exc_info.value.status_code == 409
    assert product.slug == "old-product"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("category_slug", "product_slug"),
    [
        ("current-category", "current-product"),
        ("current-category", "old-product"),
        ("old-category", "current-product"),
        ("old-category", "old-product"),
    ],
)
async def test_category_product_resolver_accepts_current_and_old_slugs(
    category_slug: str,
    product_slug: str,
) -> None:
    category = _category(slug="current-category")
    variant = _variant(sku="SKU-123")
    product = _product(slug="current-product", category=category, variants=[variant])
    alias_repository = InMemoryRouteAliasRepository(
        [
            _alias(RouteAliasEntityType.PRODUCT, entity_id=product.id, alias_slug="old-product"),
            _alias(RouteAliasEntityType.CATEGORY, entity_id=category.id, alias_slug="old-category"),
        ]
    )
    service = ProductsService(DummySession())
    service.repository = PublicProductRepository(product)  # type: ignore[assignment]
    service.categories_repository = PublicCategoryRepository(category)  # type: ignore[assignment]
    service.variants_repository.get_by_sku = AsyncMock(return_value=variant)
    service.route_aliases = _route_aliases(alias_repository)

    result = await service.resolve_public_product(
        category_slug=category_slug,
        product_slug=product_slug,
        sku="SKU-123",
        track_view=False,
    )

    assert result.product.slug == "current-product"
    assert result.route_context.category is not None
    assert result.route_context.category.slug == "current-category"
    assert result.route_context.product_slug == "current-product"
    assert result.route_context.requested_sku == "SKU-123"
    assert result.route_context.selected_variant_sku == "SKU-123"


@pytest.mark.asyncio
async def test_hidden_active_product_alias_still_opens_by_direct_link() -> None:
    product = _product(slug="current-product", is_listed=False)
    alias_repository = InMemoryRouteAliasRepository(
        [_alias(RouteAliasEntityType.PRODUCT, entity_id=product.id, alias_slug="old-product")]
    )
    service = ProductsService(DummySession())
    service.repository = PublicProductRepository(product)  # type: ignore[assignment]
    service.route_aliases = _route_aliases(alias_repository)

    result = await service.resolve_public_product(product_slug="old-product", track_view=False)

    assert result.product.id == product.id
    assert result.product.slug == "current-product"


@pytest.mark.asyncio
async def test_archived_product_alias_does_not_bypass_existing_restrictions() -> None:
    product = _product(slug="current-product", status=ProductStatus.ARCHIVED)
    alias_repository = InMemoryRouteAliasRepository(
        [_alias(RouteAliasEntityType.PRODUCT, entity_id=product.id, alias_slug="old-product")]
    )
    service = ProductsService(DummySession())
    service.repository = PublicProductRepository(product)  # type: ignore[assignment]
    service.route_aliases = _route_aliases(alias_repository)

    with pytest.raises(AppError, match="Product not found") as exc_info:
        await service.resolve_public_product(product_slug="old-product", track_view=False)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_category_current_and_old_slug_resolve_to_canonical_category() -> None:
    category = _category(slug="current-category")
    alias_repository = InMemoryRouteAliasRepository(
        [_alias(RouteAliasEntityType.CATEGORY, entity_id=category.id, alias_slug="old-category")]
    )
    service = CategoriesService(DummySession())
    service.repository = PublicCategoryRepository(category)  # type: ignore[assignment]
    service.route_aliases = _route_aliases(alias_repository)

    current = await service.resolve_category_by_slug("current-category")
    old = await service.resolve_category_by_slug("old-category")

    assert current.slug == "current-category"
    assert old.slug == "current-category"


@pytest.mark.asyncio
async def test_look_current_and_old_slug_resolve_to_canonical_look() -> None:
    look = _look(slug="current-look")
    alias_repository = InMemoryRouteAliasRepository(
        [_alias(RouteAliasEntityType.LOOK, entity_id=look.id, alias_slug="old-look")]
    )
    service = LooksService(DummySession())
    service.repository = PublicLookRepository(look)  # type: ignore[assignment]
    service.route_aliases = _route_aliases(alias_repository)

    current = await service.get_public_look("current-look")
    old = await service.get_public_look("old-look")

    assert current.slug == "current-look"
    assert old.slug == "current-look"


@pytest.mark.asyncio
async def test_unlisted_look_alias_does_not_bypass_public_rules() -> None:
    look = _look(slug="current-look", is_listed=False)
    alias_repository = InMemoryRouteAliasRepository(
        [_alias(RouteAliasEntityType.LOOK, entity_id=look.id, alias_slug="old-look")]
    )
    service = LooksService(DummySession())
    service.repository = PublicLookRepository(look)  # type: ignore[assignment]
    service.route_aliases = _route_aliases(alias_repository)

    with pytest.raises(AppError, match="Look not found") as exc_info:
        await service.get_public_look("old-look")

    assert exc_info.value.status_code == 404


def _route_aliases(repository: InMemoryRouteAliasRepository) -> RouteAliasesService:
    service = RouteAliasesService(SimpleNamespace())
    service.repository = repository  # type: ignore[assignment]
    return service


def _alias(
    entity_type: RouteAliasEntityType,
    *,
    entity_id: int,
    alias_slug: str,
) -> RouteAlias:
    return RouteAlias(
        entity_type=entity_type,
        entity_id=entity_id,
        alias_slug=alias_slug,
        is_active=True,
    )


def _category(
    *,
    category_id: int = 1,
    slug: str = "current-category",
) -> Category:
    return Category(
        id=category_id,
        name="Category",
        slug=slug,
        description=None,
        image_path=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _product(
    *,
    product_id: int = 1,
    slug: str = "current-product",
    category: Category | None = None,
    variants: list[ProductVariant] | None = None,
    status: ProductStatus = ProductStatus.ACTIVE,
    is_listed: bool = True,
) -> Product:
    category = category or _category()
    product = Product(
        id=product_id,
        name="Product",
        slug=slug,
        brand=None,
        description="Description",
        base_price=Decimal("100.00"),
        old_price=None,
        search_priority=1,
        search_aliases=None,
        size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        size_group=ProductSizeGroup.CLOTHING,
        image_badge_type=ProductImageBadgeType.NONE,
        image_badge_text=None,
        image_badge_color=None,
        image_badge_position=None,
        status=status,
        is_listed=is_listed,
        is_returnable=True,
        category_id=category.id,
        category=category,
        product_categories=[
            ProductCategory(category_id=category.id, priority=1, category=category),
        ],
        tags=[],
        images=[],
        variants=variants or [_variant(product_id=product_id)],
        related_product_links=[],
        created_at=NOW,
        updated_at=NOW,
    )
    for variant in product.variants:
        variant.product_id = product.id
    return product


def _variant(
    *,
    product_id: int = 1,
    variant_id: int = 1,
    sku: str = "SKU-123",
    is_active: bool = True,
) -> ProductVariant:
    return ProductVariant(
        id=variant_id,
        product_id=product_id,
        size="M",
        color="Black",
        sku=sku,
        stock_quantity=5,
        reserved_quantity=0,
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def _look(
    *,
    look_id: int = 1,
    slug: str = "current-look",
    status: LookStatus = LookStatus.ACTIVE,
    is_listed: bool = True,
) -> Look:
    product = _product()
    return Look(
        id=look_id,
        title="Look",
        slug=slug,
        description=None,
        status=status,
        is_listed=is_listed,
        search_priority=1,
        images=[],
        items=[
            LookItem(
                id=1,
                look_id=look_id,
                product_id=product.id,
                product=product,
                position=0,
                quantity=1,
                is_default_selected=True,
                created_at=NOW,
                updated_at=NOW,
            )
        ],
        created_at=NOW,
        updated_at=NOW,
    )
