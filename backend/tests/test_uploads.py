from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from PIL import Image
from starlette.datastructures import Headers

from app.common.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Product, ProductSizeGrid, ProductStatus, User, UserRole
from app.main import create_app
from app.modules.uploads.image_profiles import ImageUploadKind
from app.modules.uploads.router import get_uploads_service
from app.modules.uploads.service import MAX_IMAGE_SIZE_BYTES, UploadsService
from app.modules.uploads.storage import LocalStorageService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 5, 27, tzinfo=UTC)


@pytest.mark.asyncio
async def test_product_image_upload_succeeds_and_links_existing_product(tmp_path: Path) -> None:
    session = DummySession()
    service = UploadsService(session, storage=LocalStorageService(tmp_path))
    service.products_repository.get_by_id = AsyncMock(return_value=_product())
    service.repository.next_product_image_position = AsyncMock(return_value=0)
    service.repository.clear_primary_product_images = AsyncMock()
    captured = {}

    def capture_image(image: object) -> None:
        captured["image"] = image

    service.repository.add_product_image = capture_image
    content = _image_bytes(1200, 1500, "JPEG")

    image = await service.upload_product_image(
        product_id=1,
        file=_upload_file("hoodie.jpg", content, "image/jpeg"),
        alt_text="Black hoodie",
        is_primary=True,
    )

    assert image.product_id == 1
    assert image.file_path.startswith("products/")
    assert image.original_filename == "hoodie.jpg"
    assert image.mime_type == "image/jpeg"
    assert image.size_bytes == len(content)
    assert image.is_primary is True
    assert (tmp_path / image.file_path).is_file()
    assert captured["image"] is image
    service.products_repository.get_by_id.assert_awaited_once_with(1)
    service.repository.clear_primary_product_images.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_upload_rejects_invalid_extension(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    with pytest.raises(AppError, match="extension"):
        await service.upload_banner_image(
            file=_upload_file("banner.gif", b"image-bytes", "image/png")
        )


@pytest.mark.asyncio
async def test_upload_rejects_invalid_mime_type(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    with pytest.raises(AppError, match="MIME"):
        await service.upload_banner_image(
            file=_upload_file("banner.png", b"image-bytes", "text/plain")
        )


@pytest.mark.asyncio
async def test_upload_rejects_file_size_limit(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    with pytest.raises(AppError, match="size"):
        await service.upload_banner_image(
            file=_upload_file(
                "banner.png",
                b"x" * (MAX_IMAGE_SIZE_BYTES + 1),
                "image/png",
            )
        )


@pytest.mark.asyncio
async def test_product_upload_rejects_below_minimum_dimensions(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))
    service.products_repository.get_by_id = AsyncMock(return_value=_product())

    with pytest.raises(AppError, match="600x750") as exc_info:
        await service.upload_product_image(
            product_id=1,
            file=_upload_file("small-product.jpg", _image_bytes(400, 500, "JPEG"), "image/jpeg"),
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_banner_upload_rejects_below_minimum_dimensions(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    with pytest.raises(AppError, match="1200x621") as exc_info:
        await service.upload_banner_image(
            file=_upload_file("small-banner.png", _image_bytes(600, 200, "PNG"), "image/png"),
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_banner_upload_rejects_wrong_aspect_ratio(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    with pytest.raises(AppError, match="400:207") as exc_info:
        await service.upload_banner_image(
            file=_upload_file("portrait-banner.png", _image_bytes(1200, 800, "PNG"), "image/png"),
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_native_banner_upload_accepts_taller_passive_profile(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    banner = await service.upload_banner_image(
        file=_upload_file("native-promo.png", _image_bytes(2000, 1035, "PNG"), "image/png"),
        alt_text="Native promo",
    )

    assert banner.file_path.startswith("banners/")
    assert banner.mime_type == "image/png"


@pytest.mark.asyncio
async def test_banner_image_upload_stores_file_without_creating_banner(tmp_path: Path) -> None:
    session = DummySession()
    service = UploadsService(session, storage=LocalStorageService(tmp_path))
    content = _image_bytes(2000, 1035, "PNG")

    banner = await service.upload_banner_image(
        file=_upload_file("../promo.png", content, "image/png"),
        alt_text="Promo",
    )

    assert banner.file_path.startswith("banners/")
    assert banner.original_filename == "promo.png"
    assert banner.mime_type == "image/png"
    assert banner.size_bytes == len(content)
    assert banner.alt_text == "Promo"
    assert (tmp_path / banner.file_path).is_file()
    assert session.committed is False


@pytest.mark.asyncio
async def test_tag_image_upload_stores_file_in_tags_directory(tmp_path: Path) -> None:
    session = DummySession()
    service = UploadsService(session, storage=LocalStorageService(tmp_path))
    content = _image_bytes(1200, 900, "WEBP")

    image = await service.upload_tag_image(
        file=_upload_file("../premium.webp", content, "image/webp"),
        alt_text="Premium",
    )

    assert image.file_path.startswith("tags/")
    assert image.url == f"/uploads/{image.file_path}"
    assert image.original_filename == "premium.webp"
    assert image.mime_type == "image/webp"
    assert image.size_bytes == len(content)
    assert image.alt_text == "Premium"
    assert (tmp_path / image.file_path).is_file()
    assert session.committed is False


@pytest.mark.asyncio
async def test_category_image_upload_stores_file_in_categories_directory(tmp_path: Path) -> None:
    session = DummySession()
    service = UploadsService(session, storage=LocalStorageService(tmp_path))
    content = _image_bytes(1200, 900, "WEBP")

    image = await service.upload_category_image(
        file=_upload_file("../hoodies.webp", content, "image/webp"),
        alt_text="Hoodies",
    )

    assert image.file_path.startswith("categories/")
    assert image.url == f"/uploads/{image.file_path}"
    assert image.original_filename == "hoodies.webp"
    assert image.mime_type == "image/webp"
    assert image.size_bytes == len(content)
    assert image.alt_text == "Hoodies"
    assert (tmp_path / image.file_path).is_file()
    assert session.committed is False


@pytest.mark.asyncio
async def test_vertical_banner_upload_accepts_nine_to_sixteen_image(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    banner = await service.upload_banner_image(
        file=_upload_file("vertical-promo.jpg", _image_bytes(900, 1600, "JPEG"), "image/jpeg"),
        alt_text="Vertical promo",
        image_kind=ImageUploadKind.VERTICAL_BANNER,
    )

    assert banner.file_path.startswith("banners/")
    assert banner.mime_type == "image/jpeg"


@pytest.mark.asyncio
async def test_popup_banner_upload_accepts_three_to_four_image(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    banner = await service.upload_banner_image(
        file=_upload_file("popup-promo.jpg", _image_bytes(900, 1200, "JPEG"), "image/jpeg"),
        alt_text="Popup promo",
        image_kind=ImageUploadKind.POPUP_BANNER,
    )

    assert banner.file_path.startswith("banners/")
    assert banner.mime_type == "image/jpeg"


@pytest.mark.asyncio
async def test_aggressive_banner_upload_accepts_nine_to_sixteen_image(tmp_path: Path) -> None:
    service = UploadsService(DummySession(), storage=LocalStorageService(tmp_path))

    banner = await service.upload_banner_image(
        file=_upload_file("entry-promo.jpg", _image_bytes(900, 1600, "JPEG"), "image/jpeg"),
        alt_text="Entry promo",
        image_kind=ImageUploadKind.AGGRESSIVE_BANNER,
    )

    assert banner.file_path.startswith("banners/")
    assert banner.mime_type == "image/jpeg"


def test_product_upload_route_requires_seller_or_admin_auth() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/uploads/products/1/images",
            files={"file": ("hoodie.jpg", b"image-bytes", "image/jpeg")},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_product_upload_route_rejects_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/uploads/products/1/images",
                files={"file": ("hoodie.jpg", b"image-bytes", "image/jpeg")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_product_upload_route_allows_seller() -> None:
    app = create_app()

    class FakeUploadsService:
        async def upload_product_image(self, **_: object) -> dict[str, object]:
            now = datetime(2026, 5, 27, tzinfo=UTC).isoformat()
            return {
                "id": 1,
                "product_id": 1,
                "file_path": "products/generated.jpg",
                "url": "/uploads/products/generated.jpg",
                "original_filename": "hoodie.jpg",
                "mime_type": "image/jpeg",
                "size_bytes": 11,
                "alt_text": None,
                "position": 0,
                "is_primary": False,
                "created_at": now,
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_uploads_service] = lambda: FakeUploadsService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/uploads/products/1/images",
                files={"file": ("hoodie.jpg", b"image-bytes", "image/jpeg")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["product_id"] == 1
    assert response.json()["url"] == "/uploads/products/generated.jpg"


def test_banner_upload_route_allows_admin() -> None:
    app = create_app()

    class FakeUploadsService:
        async def upload_banner_image(self, **_: object) -> dict[str, object]:
            return {
                "file_path": "banners/generated.webp",
                "url": "/uploads/banners/generated.webp",
                "original_filename": "promo.webp",
                "mime_type": "image/webp",
                "size_bytes": 12,
                "alt_text": None,
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.ADMIN)
    app.dependency_overrides[get_uploads_service] = lambda: FakeUploadsService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/uploads/banners/images",
                files={"file": ("promo.webp", b"banner-bytes", "image/webp")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["url"] == "/uploads/banners/generated.webp"


def test_tag_upload_route_allows_seller() -> None:
    app = create_app()

    class FakeUploadsService:
        async def upload_tag_image(self, **_: object) -> dict[str, object]:
            return {
                "file_path": "tags/0123456789abcdef0123456789abcdef.webp",
                "url": "/uploads/tags/0123456789abcdef0123456789abcdef.webp",
                "original_filename": "premium.webp",
                "mime_type": "image/webp",
                "size_bytes": 12,
                "alt_text": "Premium",
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_uploads_service] = lambda: FakeUploadsService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/uploads/tags/images",
                files={"file": ("premium.webp", b"tag-bytes", "image/webp")},
                data={"alt_text": "Premium"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["file_path"].startswith("tags/")


def test_category_upload_route_requires_seller_or_admin_auth() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/uploads/categories/images",
            files={"file": ("hoodies.webp", b"category-bytes", "image/webp")},
        )

    assert response.status_code == 401


def test_category_upload_route_allows_seller() -> None:
    app = create_app()

    class FakeUploadsService:
        async def upload_category_image(self, **_: object) -> dict[str, object]:
            return {
                "file_path": "categories/0123456789abcdef0123456789abcdef.webp",
                "url": "/uploads/categories/0123456789abcdef0123456789abcdef.webp",
                "original_filename": "hoodies.webp",
                "mime_type": "image/webp",
                "size_bytes": 12,
                "alt_text": "Hoodies",
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_uploads_service] = lambda: FakeUploadsService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/uploads/categories/images",
                files={"file": ("hoodies.webp", b"category-bytes", "image/webp")},
                data={"alt_text": "Hoodies"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["file_path"].startswith("categories/")


def test_static_upload_path_serves_files(tmp_path: Path) -> None:
    previous_uploads_dir_path = settings.__dict__.get("uploads_dir_path")
    settings.__dict__["uploads_dir_path"] = tmp_path
    (tmp_path / "products").mkdir(parents=True)
    (tmp_path / "products" / "static-check.txt").write_text("ok", encoding="utf-8")
    try:
        with TestClient(create_app()) as client:
            response = client.get("/uploads/products/static-check.txt")
    finally:
        if previous_uploads_dir_path is None:
            settings.__dict__.pop("uploads_dir_path", None)
        else:
            settings.__dict__["uploads_dir_path"] = previous_uploads_dir_path

    assert response.status_code == 200
    assert response.text == "ok"


def _upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _image_bytes(width: int, height: int, image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), color=(124, 58, 237)).save(output, format=image_format)
    return output.getvalue()


def _product() -> Product:
    return Product(
        id=1,
        name="Hoodie",
        slug="hoodie",
        description="Warm",
        base_price=Decimal("59.90"),
        size_grid=ProductSizeGrid.CLOTHING_ALPHA,
        status=ProductStatus.DRAFT,
        category_id=None,
        images=[],
        tags=[],
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
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
        created_at=datetime(2026, 5, 27, tzinfo=UTC),
        updated_at=datetime(2026, 5, 27, tzinfo=UTC),
    )
