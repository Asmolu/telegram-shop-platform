from datetime import UTC, datetime

from fastapi import status
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import User, UserRole
from app.main import create_app
from app.modules.categories.router import get_categories_service
from app.modules.products.router import get_products_service
from app.modules.products.schemas import (
    ProductCardList,
    ProductResolveResponse,
    ProductSearchSuggestion,
    ProductSearchSuggestionList,
)
from app.modules.tags.router import get_tags_service


def test_public_product_list_allows_anonymous_access() -> None:
    app = create_app()

    class FakeProductsService:
        async def list_public_products(self, **_: object) -> ProductCardList:
            return ProductCardList(items=[], meta=PageMeta(limit=20, offset=0, total=0))

        async def track_public_product_list_search(self, **_: object) -> None:
            return None

    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": [], "meta": {"limit": 20, "offset": 0, "total": 0}}
    assert response.headers["etag"]
    assert response.headers["cache-control"] == "no-cache"


def test_public_product_list_etag_returns_304_without_search_tracking() -> None:
    app = create_app()

    class FakeProductsService:
        def __init__(self) -> None:
            self.tracked = 0

        async def list_public_products(self, **_: object) -> ProductCardList:
            return ProductCardList(items=[], meta=PageMeta(limit=20, offset=0, total=0))

        async def track_public_product_list_search(self, **_: object) -> None:
            self.tracked += 1

    service = FakeProductsService()
    app.dependency_overrides[get_products_service] = lambda: service
    try:
        with TestClient(app) as client:
            first_response = client.get("/api/v1/products?search=hoodie")
            second_response = client.get(
                "/api/v1/products?search=hoodie",
                headers={"If-None-Match": first_response.headers["etag"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert second_response.status_code == 304
    assert second_response.content == b""
    assert service.tracked == 1


def test_public_product_list_accepts_unquoted_if_none_match() -> None:
    app = create_app()

    class FakeProductsService:
        async def list_public_products(self, **_: object) -> ProductCardList:
            return ProductCardList(items=[], meta=PageMeta(limit=20, offset=0, total=0))

        async def track_public_product_list_search(self, **_: object) -> None:
            return None

    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            first_response = client.get("/api/v1/products")
            second_response = client.get(
                "/api/v1/products",
                headers={"If-None-Match": first_response.headers["etag"].strip('"')},
            )
    finally:
        app.dependency_overrides.clear()

    assert second_response.status_code == 304
    assert second_response.content == b""


def test_public_product_suggestions_allow_anonymous_access() -> None:
    app = create_app()

    class FakeProductsService:
        async def list_search_suggestions(self, **_: object) -> ProductSearchSuggestionList:
            return ProductSearchSuggestionList(
                items=[ProductSearchSuggestion(value="Hoodie", kind="product")]
            )

    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products/suggestions?query=hoo")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"value": "Hoodie", "kind": "product", "label": None}]
    }


def test_public_product_resolver_route_precedes_numeric_product_route() -> None:
    app = create_app()

    class FakeProductsService:
        def __init__(self) -> None:
            self.tracked_product_id: int | None = None

        async def resolve_public_product(self, **kwargs: object) -> ProductResolveResponse:
            assert kwargs["product_slug"] == "line-break-hoodie"
            assert kwargs["category_slug"] == "futbolki"
            assert kwargs["sku"] == "00001"
            return ProductResolveResponse.model_validate({
                "product": {
                    **_product_response(),
                    "variants": [_variant_response()],
                    "is_available": True,
                },
                "route_context": {
                    "category": {"id": 1, "slug": "futbolki", "name": "T-shirts"},
                    "product_slug": "line-break-hoodie",
                    "requested_sku": "00001",
                    "selected_variant_id": 1,
                    "selected_variant_sku": "00001",
                    "variant_status": "selected",
                },
            })

        async def track_public_product_view(self, **kwargs: object) -> None:
            self.tracked_product_id = int(kwargs["product_id"])

    service = FakeProductsService()
    app.dependency_overrides[get_products_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/products/resolve"
                "?category_slug=futbolki&product_slug=line-break-hoodie&sku=00001"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["route_context"]["variant_status"] == "selected"
    assert response.json()["route_context"]["selected_variant_sku"] == "00001"
    assert service.tracked_product_id == 1


def test_product_create_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/products", json=_product_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_product_create_rejects_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/products", json=_product_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_product_variant_create_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/products/1/variants", json=_variant_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_product_variant_create_rejects_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/products/1/variants", json=_variant_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_product_admin_list_rejects_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products/admin")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_category_and_tag_write_routes_are_protected() -> None:
    with TestClient(create_app()) as client:
        category_response = client.post(
            "/api/v1/categories",
            json={"name": "Hoodies", "slug": "hoodies", "description": None},
        )
        tag_response = client.post("/api/v1/tags", json={"name": "Premium", "slug": "premium"})

    assert category_response.status_code == 401
    assert tag_response.status_code == 401


def test_public_tag_list_includes_image_url() -> None:
    app = create_app()

    class FakeTagsService:
        async def list_tags(self) -> list[dict[str, object]]:
            now = datetime(2026, 6, 13, tzinfo=UTC).isoformat()
            return [
                {
                    "id": 1,
                    "name": "Premium",
                    "slug": "premium",
                    "image_path": "tags/0123456789abcdef0123456789abcdef.webp",
                    "image_url": "/uploads/tags/0123456789abcdef0123456789abcdef.webp",
                    "created_at": now,
                    "updated_at": now,
                }
            ]

    app.dependency_overrides[get_tags_service] = lambda: FakeTagsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/tags")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["image_url"].startswith("/uploads/tags/")


def test_public_category_list_includes_image_url() -> None:
    app = create_app()

    class FakeCategoriesService:
        async def list_categories(self) -> list[dict[str, object]]:
            now = datetime(2026, 6, 13, tzinfo=UTC).isoformat()
            return [
                {
                    "id": 1,
                    "name": "Hoodies",
                    "slug": "hoodies",
                    "description": None,
                    "image_path": "categories/0123456789abcdef0123456789abcdef.webp",
                    "image_url": "/uploads/categories/0123456789abcdef0123456789abcdef.webp",
                    "created_at": now,
                    "updated_at": now,
                }
            ]

    app.dependency_overrides[get_categories_service] = lambda: FakeCategoriesService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/categories")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["image_url"].startswith("/uploads/categories/")


def test_product_create_allows_seller() -> None:
    app = create_app()

    class FakeProductsService:
        async def create_product(self, _: object, **__: object) -> dict[str, object]:
            now = datetime(2026, 5, 27, tzinfo=UTC).isoformat()
            return {
                "id": 1,
                "name": "Hoodie",
                "slug": "hoodie",
                "description": "Warm",
                "base_price": "59.90",
                "status": "DRAFT",
                "category_id": None,
                "category": None,
                "tags": [],
                "images": [],
                "related_product_ids": [],
                "related_products": [],
                "created_at": now,
                "updated_at": now,
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/products", json=_product_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["slug"] == "hoodie"
    assert response.json()["related_product_ids"] == []
    assert response.json()["related_products"] == []


def test_product_create_allows_missing_slug_for_backend_generation() -> None:
    app = create_app()

    class FakeProductsService:
        async def create_product(self, payload: object, **__: object) -> dict[str, object]:
            assert payload.slug is None  # type: ignore[attr-defined]
            return {**_product_response(), "slug": "00001"}

    payload = _product_payload()
    del payload["slug"]

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/products", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["slug"] == "00001"


def test_product_create_returns_related_products_for_seller() -> None:
    app = create_app()

    class FakeProductsService:
        async def create_product(self, _: object, **__: object) -> dict[str, object]:
            related = _product_response()
            related["id"] = 2
            related["slug"] = "related-hoodie"
            product = _product_response()
            product["related_product_ids"] = [2]
            product["related_products"] = [related]
            return product

    payload = _product_payload()
    payload["slug"] = "hoodie-with-related"
    payload["related_product_ids"] = [2]

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/products", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["related_product_ids"] == [2]
    assert response.json()["related_products"][0]["id"] == 2


def test_product_variant_create_allows_seller() -> None:
    app = create_app()

    class FakeProductsService:
        async def create_product_variant(
            self,
            _: int,
            __: object,
            **___: object,
        ) -> dict[str, object]:
            return _variant_response()

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/products/1/variants", json=_variant_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["available_quantity"] == 3


def test_product_variant_create_allows_missing_sku_for_backend_generation() -> None:
    app = create_app()

    class FakeProductsService:
        async def create_product_variant(
            self,
            _: int,
            payload: object,
            **___: object,
        ) -> dict[str, object]:
            assert payload.sku is None  # type: ignore[attr-defined]
            return {**_variant_response(), "sku": "00001"}

    variant_payload = _variant_payload()
    del variant_payload["sku"]

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/products/1/variants", json=variant_payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["sku"] == "00001"


def test_product_variant_sku_generation_allows_seller() -> None:
    app = create_app()

    class FakeProductsService:
        async def generate_variant_skus(self, count: int) -> dict[str, object]:
            assert count == 2
            return {"items": ["00001", "00002"]}

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products/admin/variant-skus/next?count=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": ["00001", "00002"]}


def test_product_slug_generation_allows_seller() -> None:
    app = create_app()

    class FakeProductsService:
        async def generate_product_slugs(self, count: int) -> dict[str, object]:
            assert count == 2
            return {"items": ["00001", "00002"]}

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products/admin/slugs/next?count=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": ["00001", "00002"]}


def test_product_slug_generation_exhaustion_returns_clear_400() -> None:
    app = create_app()

    class FakeProductsService:
        async def generate_product_slugs(self, _: int) -> dict[str, object]:
            raise AppError(
                "Numeric product slug range 00001-99999 is exhausted.",
                status.HTTP_400_BAD_REQUEST,
            )

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products/admin/slugs/next")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Numeric product slug range 00001-99999 is exhausted."
    }


def test_product_status_and_archive_routes_are_protected() -> None:
    with TestClient(create_app()) as client:
        status_response = client.patch("/api/v1/products/1/status", json={"status": "ACTIVE"})
        archive_response = client.patch("/api/v1/products/1/archive")
        variant_response = client.patch("/api/v1/products/variants/1/deactivate")

    assert status_response.status_code == 401
    assert archive_response.status_code == 401
    assert variant_response.status_code == 401


def test_product_archive_allows_seller() -> None:
    app = create_app()

    class FakeProductsService:
        async def archive_product(self, _: int, **__: object) -> dict[str, object]:
            return {**_product_response(), "status": "ARCHIVED", "variants": []}

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.patch("/api/v1/products/1/archive")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "ARCHIVED"


def test_product_variant_deactivate_allows_seller() -> None:
    app = create_app()

    class FakeProductsService:
        async def deactivate_product_variant(self, _: int, **__: object) -> dict[str, object]:
            return {**_variant_response(), "is_active": False}

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.patch("/api/v1/products/variants/1/deactivate")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_product_variant_create_rejects_negative_stock() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/products/1/variants",
                json={**_variant_payload(), "stock_quantity": -1},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_product_variant_create_rejects_reserved_quantity_above_stock() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/products/1/variants",
                json={**_variant_payload(), "stock_quantity": 2, "reserved_quantity": 3},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_public_product_list_includes_active_variants_and_availability() -> None:
    app = create_app()

    class FakeProductsService:
        async def list_public_products(self, **_: object) -> ProductCardList:
            return ProductCardList.model_validate(
                {
                    "items": [
                        {
                            **_product_response(),
                            "brand": "ICON STORE",
                            "image_badge_color": "green",
                            "image_badge_position": "bottom-right",
                            "variants": [_variant_response()],
                            "is_available": True,
                        }
                    ],
                    "meta": {"limit": 20, "offset": 0, "total": 1},
                }
            )

        async def track_public_product_list_search(self, **_: object) -> None:
            return None

    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["is_available"] is True
    assert response.json()["items"][0]["brand"] == "ICON STORE"
    assert response.json()["items"][0]["size_grid"] == "clothing_alpha"
    assert response.json()["items"][0]["image_badge_color"] == "green"
    assert response.json()["items"][0]["image_badge_position"] == "bottom-right"
    assert response.json()["items"][0]["variants"][0]["available_quantity"] == 3
    assert "description" not in response.json()["items"][0]
    assert "images" not in response.json()["items"][0]
    assert "tags" not in response.json()["items"][0]
    assert "sku" not in response.json()["items"][0]["variants"][0]


def test_public_product_variants_returns_active_variants() -> None:
    app = create_app()

    class FakeProductsService:
        async def list_public_product_variants(self, _: int) -> dict[str, object]:
            return {"items": [_variant_response()]}

    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products/1/variants")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["is_active"] is True


def _product_payload() -> dict[str, object]:
    return {
        "name": "Hoodie",
        "slug": "hoodie",
        "description": "Warm",
        "base_price": "59.90",
        "status": "DRAFT",
        "category_id": None,
        "tag_ids": [],
        "images": [],
        "related_product_ids": [],
    }


def _variant_payload() -> dict[str, object]:
    return {
        "size": "M",
        "color": "Black",
        "sku": "HOODIE-M-BLK",
        "stock_quantity": 5,
        "reserved_quantity": 2,
        "is_active": True,
    }


def _product_response() -> dict[str, object]:
    now = datetime(2026, 5, 27, tzinfo=UTC).isoformat()
    return {
        "id": 1,
        "name": "Hoodie",
        "slug": "hoodie",
        "brand": None,
        "description": "Warm",
        "base_price": "59.90",
        "size_grid": "clothing_alpha",
        "image_badge_color": None,
        "image_badge_position": None,
        "status": "ACTIVE",
        "category_id": None,
        "category": None,
        "tags": [],
        "images": [],
        "created_at": now,
        "updated_at": now,
    }


def _variant_response() -> dict[str, object]:
    now = datetime(2026, 5, 27, tzinfo=UTC).isoformat()
    return {
        "id": 1,
        "product_id": 1,
        "size": "M",
        "color": "Black",
        "sku": "HOODIE-M-BLK",
        "stock_quantity": 5,
        "reserved_quantity": 2,
        "available_quantity": 3,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }


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
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )
