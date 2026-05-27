from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.common.pagination import PageMeta
from app.db.models import User, UserRole
from app.main import create_app
from app.modules.products.router import get_products_service
from app.modules.products.schemas import ProductList


def test_public_product_list_allows_anonymous_access() -> None:
    app = create_app()

    class FakeProductsService:
        async def list_public_products(self, **_: object) -> ProductList:
            return ProductList(items=[], meta=PageMeta(limit=20, offset=0, total=0))

    app.dependency_overrides[get_products_service] = lambda: FakeProductsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"items": [], "meta": {"limit": 20, "offset": 0, "total": 0}}


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


def test_category_and_tag_write_routes_are_protected() -> None:
    with TestClient(create_app()) as client:
        category_response = client.post(
            "/api/v1/categories",
            json={"name": "Hoodies", "slug": "hoodies", "description": None},
        )
        tag_response = client.post("/api/v1/tags", json={"name": "Premium", "slug": "premium"})

    assert category_response.status_code == 401
    assert tag_response.status_code == 401


def test_product_create_allows_seller() -> None:
    app = create_app()

    class FakeProductsService:
        async def create_product(self, _: object) -> dict[str, object]:
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
