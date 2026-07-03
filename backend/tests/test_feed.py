from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.common.pagination import PageMeta
from app.db.models import (
    Look,
    LookItem,
    LookStatus,
    Product,
    ProductImageBadgeType,
    ProductSizeGrid,
    ProductSizeGroup,
    ProductStatus,
    ProductVariant,
)
from app.main import create_app
from app.modules.feed.repository import FeedItemRef
from app.modules.feed.router import get_feed_service
from app.modules.feed.schemas import FeedListResponse
from app.modules.feed.service import FeedService

NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


class FakeFeedRepository:
    def __init__(
        self,
        *,
        products: list[Product] | None = None,
        looks: list[Look] | None = None,
    ) -> None:
        self.products = products or []
        self.looks = looks or []

    async def list_public_refs(self, *, limit: int, offset: int) -> tuple[list[FeedItemRef], int]:
        refs = [
            (product.search_priority, product.created_at, 0, product.id, "product")
            for product in self.products
            if product.status == ProductStatus.ACTIVE and product.is_listed
        ]
        refs.extend(
            (look.search_priority, look.created_at, 1, look.id, "look")
            for look in self.looks
            if look.status == LookStatus.ACTIVE and look.is_listed
        )
        ordered_refs = sorted(
            refs,
            key=lambda item: (item[0], -item[1].timestamp(), item[2], -item[3]),
        )
        page = ordered_refs[offset : offset + limit]
        return [
            FeedItemRef(item_type=item_type, item_id=item_id)
            for _priority, _created_at, _type_rank, item_id, item_type in page
        ], len(ordered_refs)

    async def list_public_products_by_ids(self, product_ids: list[int]) -> list[Product]:
        return [
            product
            for product in self.products
            if product.id in product_ids
            and product.status == ProductStatus.ACTIVE
            and product.is_listed
        ]

    async def list_public_looks_by_ids(self, look_ids: list[int]) -> list[Look]:
        return [
            look
            for look in self.looks
            if look.id in look_ids
            and look.status == LookStatus.ACTIVE
            and look.is_listed
        ]


def test_public_feed_route_returns_discriminated_items() -> None:
    app = create_app()

    class FakeFeedService:
        async def list_public_feed(self, **kwargs: object) -> FeedListResponse:
            assert kwargs == {"limit": 2, "offset": 1}
            return FeedListResponse.model_validate(
                {
                    "items": [
                        {"type": "product", "product": _product_card_payload()},
                        {"type": "look", "look": _look_card_payload()},
                    ],
                    "meta": {"limit": 2, "offset": 1, "total": 4},
                }
            )

    app.dependency_overrides[get_feed_service] = lambda: FakeFeedService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/feed?limit=2&offset=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["etag"]
    assert response.headers["cache-control"] == "no-cache"
    assert response.json()["items"][0]["type"] == "product"
    assert response.json()["items"][0]["product"]["slug"] == "active-product"
    assert response.json()["items"][1]["type"] == "look"
    assert response.json()["items"][1]["look"]["slug"] == "active-look"
    assert response.json()["meta"] == {"limit": 2, "offset": 1, "total": 4}


def test_public_feed_route_etag_returns_304() -> None:
    app = create_app()

    class FakeFeedService:
        async def list_public_feed(self, **_: object) -> FeedListResponse:
            return FeedListResponse(items=[], meta=PageMeta(limit=20, offset=0, total=0))

    app.dependency_overrides[get_feed_service] = lambda: FakeFeedService()
    try:
        with TestClient(app) as client:
            first_response = client.get("/api/v1/feed")
            second_response = client.get(
                "/api/v1/feed",
                headers={"If-None-Match": first_response.headers["etag"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert second_response.status_code == 304
    assert second_response.content == b""


@pytest.mark.asyncio
async def test_feed_includes_only_active_listed_products_and_looks() -> None:
    hidden_component = _product(product_id=10, slug="hidden-component", is_listed=False)
    service = _feed_service(
        products=[
            _product(product_id=1, slug="active-product"),
            _product(product_id=2, slug="hidden-product", is_listed=False),
            _product(product_id=3, slug="draft-product", status_value=ProductStatus.DRAFT),
        ],
        looks=[
            _look(look_id=1, slug="active-look", product=hidden_component),
            _look(look_id=2, slug="draft-look", status_value=LookStatus.DRAFT),
            _look(look_id=3, slug="archived-look", status_value=LookStatus.ARCHIVED),
            _look(look_id=4, slug="unlisted-look", is_listed=False),
        ],
    )

    feed = await service.list_public_feed(limit=20, offset=0)

    assert _feed_keys(feed) == ["product:active-product", "look:active-look"]
    assert feed.meta.total == 2
    look_item = next(item for item in feed.items if item.type == "look")
    assert look_item.look.price == hidden_component.base_price
    assert "product:hidden-component" not in _feed_keys(feed)


@pytest.mark.asyncio
async def test_feed_pagination_and_sorting_are_stable() -> None:
    service = _feed_service(
        products=[
            _product(
                product_id=1,
                slug="first-product",
                search_priority=1,
                created_at=NOW,
            ),
            _product(
                product_id=2,
                slug="older-product",
                search_priority=1,
                created_at=NOW - timedelta(hours=1),
            ),
            _product(
                product_id=3,
                slug="lower-priority-product",
                search_priority=2,
                created_at=NOW + timedelta(hours=1),
            ),
        ],
        looks=[
            _look(
                look_id=1,
                slug="same-time-look",
                search_priority=1,
                created_at=NOW,
            ),
        ],
    )

    first_page = await service.list_public_feed(limit=2, offset=0)
    second_page = await service.list_public_feed(limit=2, offset=2)

    assert _feed_keys(first_page) == ["product:first-product", "look:same-time-look"]
    assert _feed_keys(second_page) == ["product:older-product", "product:lower-priority-product"]
    assert first_page.meta.total == 4
    assert second_page.meta.total == 4


def _feed_service(*, products: list[Product], looks: list[Look]) -> FeedService:
    service = FeedService(object())  # type: ignore[arg-type]
    service.repository = FakeFeedRepository(products=products, looks=looks)  # type: ignore[assignment]
    return service


def _feed_keys(feed: FeedListResponse) -> list[str]:
    keys: list[str] = []
    for item in feed.items:
        if item.type == "product":
            keys.append(f"product:{item.product.slug}")
        else:
            keys.append(f"look:{item.look.slug}")
    return keys


def _product(
    *,
    product_id: int,
    slug: str,
    status_value: ProductStatus = ProductStatus.ACTIVE,
    is_listed: bool = True,
    search_priority: int = 1,
    created_at: datetime = NOW,
) -> Product:
    product = Product(
        id=product_id,
        name=slug.replace("-", " ").title(),
        slug=slug,
        brand="ICON STORE",
        description=None,
        base_price=Decimal("1000.00"),
        old_price=None,
        search_priority=search_priority,
        size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        size_group=ProductSizeGroup.CLOTHING,
        image_badge_type=ProductImageBadgeType.NONE,
        image_badge_text=None,
        image_badge_color=None,
        image_badge_position=None,
        status=status_value,
        is_listed=is_listed,
        is_returnable=True,
        category_id=None,
        images=[],
        variants=[
            ProductVariant(
                id=product_id,
                product_id=product_id,
                size="M",
                color="Black",
                sku=f"SKU-{product_id}",
                stock_quantity=3,
                reserved_quantity=0,
                is_active=True,
                created_at=created_at,
                updated_at=created_at,
            )
        ],
        created_at=created_at,
        updated_at=created_at,
    )
    for variant in product.variants:
        variant.product = product
    return product


def _look(
    *,
    look_id: int,
    slug: str,
    product: Product | None = None,
    status_value: LookStatus = LookStatus.ACTIVE,
    is_listed: bool = True,
    search_priority: int = 1,
    created_at: datetime = NOW,
) -> Look:
    component = product or _product(product_id=look_id + 100, slug=f"{slug}-product")
    item = LookItem(
        id=look_id,
        look_id=look_id,
        product_id=component.id,
        product=component,
        position=0,
        quantity=1,
        is_default_selected=True,
        created_at=created_at,
        updated_at=created_at,
    )
    return Look(
        id=look_id,
        title=slug.replace("-", " ").title(),
        slug=slug,
        description=None,
        status=status_value,
        is_listed=is_listed,
        search_priority=search_priority,
        images=[],
        items=[item],
        created_at=created_at,
        updated_at=created_at,
    )


def _product_card_payload() -> dict[str, object]:
    return {
        "id": 1,
        "name": "Active Product",
        "slug": "active-product",
        "brand": "ICON STORE",
        "base_price": "1000.00",
        "old_price": None,
        "size_grid": "clothing_alpha",
        "size_group": "CLOTHING",
        "image_badge_type": "none",
        "image_badge_text": None,
        "image_badge_color": None,
        "image_badge_position": None,
        "image_url": None,
        "thumbnail_image_url": None,
        "variants": [],
        "is_available": False,
        "created_at": NOW.isoformat(),
    }


def _look_card_payload() -> dict[str, object]:
    return {
        "id": 1,
        "slug": "active-look",
        "title": "Active Look",
        "description": None,
        "primary_image_url": None,
        "price": "1000.00",
        "old_price": None,
        "item_count": 1,
        "is_available": True,
        "available_sizes": ["M"],
    }
