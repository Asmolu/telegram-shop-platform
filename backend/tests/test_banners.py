from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.errors import AppError
from app.db.models import Banner, BannerTargetType, User, UserRole
from app.main import create_app
from app.modules.banners.router import get_banners_service
from app.modules.banners.schemas import BannerCreate, BannerUpdate
from app.modules.banners.service import BannersService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, banner: Banner) -> None:
        if getattr(banner, "id", None) is None:
            banner.id = 1
        if getattr(banner, "created_at", None) is None:
            banner.created_at = _now()
        if getattr(banner, "updated_at", None) is None:
            banner.updated_at = _now()


class FakeBannersRepository:
    def __init__(self) -> None:
        self.banners: dict[int, Banner] = {}
        self.next_banner_id = 1

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        active_only: bool = False,
    ) -> tuple[list[Banner], int]:
        items = list(self.banners.values())
        if active_only:
            items = [banner for banner in items if banner.is_active]
        return items[offset : offset + limit], len(items)

    async def get_by_id(self, banner_id: int) -> Banner | None:
        return self.banners.get(banner_id)

    def add(self, banner: Banner) -> None:
        banner.id = self.next_banner_id
        self.next_banner_id += 1
        banner.created_at = _now()
        banner.updated_at = _now()
        self.banners[banner.id] = banner


@pytest.mark.asyncio
async def test_create_and_update_banner() -> None:
    service, repository, session = _banners_service()

    created = await service.create_banner(BannerCreate(**_banner_payload()))
    updated = await service.update_banner(created.id, BannerUpdate(is_active=True, position=2))

    assert created.title == "Spring drop"
    assert created.image_path == "banners/spring.webp"
    assert repository.banners[1].target_type == BannerTargetType.PRODUCT
    assert updated.is_active is True
    assert updated.position == 2
    assert session.committed is True


@pytest.mark.asyncio
async def test_public_banner_list_only_returns_active_banners() -> None:
    service, repository, _ = _banners_service()
    repository.add(_banner(is_active=True))
    repository.add(_banner(is_active=False, title="Inactive"))

    banners = await service.list_public_banners(limit=20, offset=0)

    assert len(banners.items) == 1
    assert banners.items[0].is_active is True


@pytest.mark.asyncio
async def test_activate_requires_complete_target() -> None:
    service, repository, _ = _banners_service()
    incomplete = _banner(target_type=None, target_id=None)
    repository.add(incomplete)

    with pytest.raises(AppError, match="target_type"):
        await service.set_banner_active(incomplete.id, True)


def test_banner_management_requires_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/banners/admin", json=_banner_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_banner_management_rejects_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/banners/admin", json=_banner_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_banner_management_allows_seller() -> None:
    app = create_app()

    class FakeBannersService:
        async def create_banner(self, _: BannerCreate) -> dict[str, object]:
            return _banner_response()

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_banners_service] = lambda: FakeBannersService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/banners/admin", json=_banner_payload())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["target_type"] == "product"


def test_public_active_banner_list_is_anonymous() -> None:
    app = create_app()

    class FakeBannersService:
        async def list_public_banners(self, **_: object) -> dict[str, object]:
            return {"items": [_banner_response()], "meta": {"limit": 20, "offset": 0, "total": 1}}

    app.dependency_overrides[get_banners_service] = lambda: FakeBannersService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/banners")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["is_active"] is True


def _banners_service() -> tuple[BannersService, FakeBannersRepository, DummySession]:
    session = DummySession()
    service = BannersService(session)
    repository = FakeBannersRepository()
    service.repository = repository
    return service, repository, session


def _banner(
    *,
    title: str = "Spring drop",
    is_active: bool = True,
    target_type: BannerTargetType | None = BannerTargetType.PRODUCT,
    target_id: int | None = 1,
) -> Banner:
    return Banner(
        title=title,
        subtitle="Fresh arrivals",
        file_path="banners/spring.webp",
        original_filename="spring.webp",
        mime_type="image/webp",
        size_bytes=12,
        alt_text=title,
        target_type=target_type,
        target_id=target_id,
        external_url=None,
        position=0,
        is_active=is_active,
        starts_at=None,
        ends_at=None,
        created_at=_now(),
        updated_at=_now(),
    )


def _banner_payload() -> dict[str, object]:
    return {
        "title": "Spring drop",
        "subtitle": "Fresh arrivals",
        "image_path": "banners/spring.webp",
        "target_type": "product",
        "target_id": 1,
        "external_url": None,
        "position": 0,
        "is_active": False,
        "starts_at": None,
        "ends_at": None,
    }


def _banner_response() -> dict[str, object]:
    now = _now().isoformat()
    return {
        **_banner_payload(),
        "id": 1,
        "image_url": "/uploads/banners/spring.webp",
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
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 5, 27, tzinfo=UTC)
