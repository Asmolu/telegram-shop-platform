from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import DEFAULT_JWT_SECRET_KEY, Settings, join_public_url, settings
from app.core.rate_limit import reset_in_memory_rate_limiter
from app.db.models import Category, Product, ProductImageBadgeType, ProductSizeGrid, ProductStatus
from app.main import create_app
from app.modules.products.schemas import ProductCardList, ProductUpdate
from app.modules.products.service import ProductsService


class DummySession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def refresh(self, _: object) -> None:
        return None

    async def flush(self) -> None:
        return None


class FakeCache:
    def __init__(self) -> None:
        self.models: dict[str, object] = {}
        self.deleted_keys: list[str] = []
        self.deleted_patterns: list[str] = []

    async def get_model(self, key: str, _: type) -> object | None:
        return self.models.get(key)

    async def set_model(self, key: str, value: object, _: int) -> None:
        self.models[key] = value

    async def delete(self, *keys: str) -> None:
        self.deleted_keys.extend(keys)

    async def delete_patterns(self, *patterns: str) -> None:
        self.deleted_patterns.extend(patterns)


@pytest.mark.asyncio
async def test_public_product_list_uses_cache_after_miss() -> None:
    cache = FakeCache()
    service = ProductsService(DummySession(), cache=cache)
    service.repository.list_public_cards = AsyncMock(return_value=([_product()], 1))

    first = await service.list_public_products(limit=20, offset=0)
    second = await service.list_public_products(limit=20, offset=0)

    assert isinstance(first, ProductCardList)
    assert second.meta.total == 1
    service.repository.list_public_cards.assert_awaited_once()


@pytest.mark.asyncio
async def test_product_update_invalidates_public_product_cache() -> None:
    cache = FakeCache()
    product = _product(status=ProductStatus.DRAFT)
    service = ProductsService(DummySession(), cache=cache)
    service.repository.get_by_id = AsyncMock(return_value=product)

    await service.update_product(1, ProductUpdate(status=ProductStatus.ACTIVE))

    assert cache.deleted_patterns


def test_rate_limiter_returns_429_for_limited_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_in_memory_rate_limiter()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_redis_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_auth_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_auth_window_seconds", 60)

    with TestClient(create_app()) as client:
        first = client.post("/api/v1/auth/telegram/login", json={"init_data": "bad"})
        second = client.post("/api/v1/auth/telegram/login", json={"init_data": "bad"})

    reset_in_memory_rate_limiter()
    assert first.status_code != 429
    assert second.status_code == 429
    assert second.json() == {"detail": "Rate limit exceeded"}


def test_request_id_header_is_returned() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-request-id"})

    assert response.headers["x-request-id"] == "test-request-id"


def test_production_settings_reject_default_jwt_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(app_env="production", jwt_secret_key=DEFAULT_JWT_SECRET_KEY)


def test_production_settings_reject_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            app_env="production",
            jwt_secret_key="production-secret",
            CORS_ORIGINS="*",
        )


def test_public_url_settings_normalize_trailing_slashes() -> None:
    production_settings = Settings(
        public_api_base_url="https://api.stylexac.ru/",
        public_mini_app_base_url="https://mini.stylexac.ru/",
        public_seller_panel_base_url="https://seller.stylexac.ru/",
        public_uploads_url="https://api.stylexac.ru/uploads/",
    )

    assert production_settings.public_api_base_url == "https://api.stylexac.ru"
    assert production_settings.public_mini_app_base_url == "https://mini.stylexac.ru"
    assert production_settings.public_seller_panel_base_url == "https://seller.stylexac.ru"
    assert production_settings.public_uploads_url == "https://api.stylexac.ru/uploads"
    assert production_settings.public_uploads_mount_path == "/uploads"
    assert production_settings.public_upload_url_for("/uploads/products/hoodie.jpg") == (
        "https://api.stylexac.ru/uploads/products/hoodie.jpg"
    )


def test_join_public_url_avoids_duplicate_slashes() -> None:
    assert join_public_url("https://mini.stylexac.ru/", "/product/42") == (
        "https://mini.stylexac.ru/product/42"
    )


def _product(status: ProductStatus = ProductStatus.ACTIVE) -> Product:
    return Product(
        id=1,
        name="Hoodie",
        slug="hoodie",
        description="Warm",
        base_price=Decimal("59.90"),
        size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        image_badge_type=ProductImageBadgeType.NONE,
        image_badge_text=None,
        image_badge_color=None,
        image_badge_position=None,
        status=status,
        category_id=1,
        category=Category(
            id=1,
            name="Hoodies",
            slug="hoodies",
            description=None,
            created_at=_now(),
            updated_at=_now(),
        ),
        tags=[],
        images=[],
        variants=[],
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 5, 27, tzinfo=UTC)
