from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.core.errors import AppError
from app.db.models import SellerPaymentSettings, User, UserRole
from app.main import create_app
from app.modules.settings.router import get_settings_service
from app.modules.settings.schemas import PaymentSuccessBannerSettingsRead
from app.modules.settings.service import SettingsService


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.refreshed: list[object] = []

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, instance: object) -> None:
        self.refreshed.append(instance)


class FakeSettingsRepository:
    def __init__(self, payment_settings: SellerPaymentSettings | None = None) -> None:
        self.payment_settings = payment_settings

    async def get_payment_settings(self) -> SellerPaymentSettings | None:
        return self.payment_settings

    def add(self, instance: SellerPaymentSettings) -> None:
        self.payment_settings = instance


class FakeAuditService:
    def __init__(self) -> None:
        self.logs: list[dict[str, object]] = []

    async def record_action(self, **payload: object) -> None:
        self.logs.append(payload)


@pytest.mark.asyncio
async def test_payment_success_banner_settings_default_disabled() -> None:
    service, _, _, _ = _service()

    settings = await service.get_payment_success_banner_settings()

    assert settings.enabled is False
    assert settings.image_path is None
    assert settings.image_url is None


@pytest.mark.asyncio
async def test_payment_success_banner_settings_update_stores_image_and_enabled_state() -> None:
    service, repository, session, audit = _service()

    settings = await service.update_payment_success_banner_settings(
        _payload(enabled=True, image_path="banners/paid.webp"),
        actor_user_id=2,
    )

    assert settings.enabled is True
    assert settings.image_path == "banners/paid.webp"
    assert settings.image_url == "/uploads/banners/paid.webp"
    assert repository.payment_settings is not None
    assert repository.payment_settings.payment_success_banner_enabled is True
    assert repository.payment_settings.payment_success_banner_image_path == "banners/paid.webp"
    assert repository.payment_settings.updated_by_user_id == 2
    assert session.committed is True
    assert audit.logs[0]["action"] == "payment_success_banner.settings_updated"


@pytest.mark.asyncio
async def test_payment_success_banner_settings_rejects_enabled_without_image() -> None:
    service, _, session, _ = _service()

    with pytest.raises(AppError, match="Payment success banner image is required"):
        await service.update_payment_success_banner_settings(
            _payload(enabled=True, image_path=None),
            actor_user_id=2,
        )

    assert session.committed is False


@pytest.mark.asyncio
async def test_payment_success_banner_settings_delete_disables_and_clears_image() -> None:
    existing = SellerPaymentSettings(
        id=1,
        payment_success_banner_enabled=True,
        payment_success_banner_image_path="banners/paid.webp",
        created_at=_now(),
        updated_at=_now(),
    )
    service, repository, session, audit = _service(existing)

    settings = await service.delete_payment_success_banner_settings(actor_user_id=2)

    assert settings.enabled is False
    assert settings.image_path is None
    assert repository.payment_settings is existing
    assert existing.payment_success_banner_enabled is False
    assert existing.payment_success_banner_image_path is None
    assert existing.updated_by_user_id == 2
    assert session.committed is True
    assert audit.logs[0]["action"] == "payment_success_banner.settings_deleted"


def test_payment_success_banner_settings_routes_reject_regular_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/settings/admin/payment-success-banner",
                json={"enabled": False, "image_path": None},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_payment_success_banner_settings_routes_allow_seller() -> None:
    app = create_app()

    class FakeSettingsService:
        async def get_payment_success_banner_settings(self) -> PaymentSuccessBannerSettingsRead:
            return PaymentSuccessBannerSettingsRead(
                enabled=True,
                image_path="banners/paid.webp",
                image_url="/uploads/banners/paid.webp",
                updated_at=None,
            )

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_settings_service] = lambda: FakeSettingsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/settings/admin/payment-success-banner")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["image_url"] == "/uploads/banners/paid.webp"


def _service(
    payment_settings: SellerPaymentSettings | None = None,
) -> tuple[SettingsService, FakeSettingsRepository, DummySession, FakeAuditService]:
    session = DummySession()
    audit = FakeAuditService()
    service = SettingsService(session, audit_service=audit)
    repository = FakeSettingsRepository(payment_settings)
    service.repository = repository
    return service, repository, session, audit


def _payload(*, enabled: bool, image_path: str | None):
    from app.modules.settings.schemas import PaymentSuccessBannerSettingsUpdate

    return PaymentSuccessBannerSettingsUpdate.model_validate(
        {"enabled": enabled, "image_path": image_path}
    )


def _user(role: UserRole) -> User:
    return User(
        id=2,
        telegram_id=200,
        username="seller",
        first_name="Ada",
        last_name=None,
        role=role,
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )


def _now() -> datetime:
    return datetime(2026, 7, 4, tzinfo=UTC)
