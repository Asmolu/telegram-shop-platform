from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_current_user
from app.db.models import AnalyticsEvent, AuditLog, User, UserRole
from app.main import create_app
from app.modules.analytics.router import get_analytics_service
from app.modules.analytics.service import AnalyticsService
from app.modules.audit.router import get_audit_service


def test_analytics_and_audit_models_exist() -> None:
    assert AnalyticsEvent.__tablename__ == "analytics_events"
    assert AuditLog.__tablename__ == "audit_logs"


def test_seller_can_list_analytics_events() -> None:
    app = create_app()

    class FakeAnalyticsService:
        async def list_events(self, **_: object) -> dict[str, object]:
            return {
                "items": [
                    {
                        "id": 1,
                        "event_name": "product.viewed",
                        "user_id": None,
                        "product_id": 7,
                        "order_id": None,
                        "promo_code_id": None,
                        "banner_id": None,
                        "metadata": {"source": "product_detail"},
                        "created_at": _now().isoformat(),
                    }
                ],
                "meta": {"limit": 20, "offset": 0, "total": 1},
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_analytics_service] = lambda: FakeAnalyticsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/analytics/events?event_name=product.viewed")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["event_name"] == "product.viewed"


def test_seller_can_filter_analytics_events_by_promo_and_banner() -> None:
    app = create_app()

    class FakeAnalyticsService:
        async def list_events(self, **payload: object) -> dict[str, object]:
            assert payload["event_name"] == "banner.clicked"
            assert payload["promo_code_id"] == 7
            assert payload["banner_id"] == 3
            return {
                "items": [
                    {
                        "id": 1,
                        "event_name": "banner.clicked",
                        "user_id": 2,
                        "product_id": None,
                        "order_id": None,
                        "promo_code_id": 7,
                        "banner_id": 3,
                        "metadata": {"source": "main"},
                        "created_at": _now().isoformat(),
                    }
                ],
                "meta": {"limit": 20, "offset": 0, "total": 1},
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_analytics_service] = lambda: FakeAnalyticsService()
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/analytics/events"
                "?event_name=banner.clicked&promo_code_id=7&banner_id=3"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["banner_id"] == 3


def test_seller_can_access_analytics_summary() -> None:
    app = create_app()

    class FakeAnalyticsService:
        async def get_summary(self, **_: object) -> dict[str, object]:
            return {
                "total_orders": 3,
                "total_revenue": "179.70",
                "product_views_count": 10,
                "cart_item_added_count": 4,
                "checkout_started_count": 3,
                "order_created_count": 3,
                "promo_used_count": 1,
                "banner_clicked_count": 2,
                "top_products": [
                    {"product_id": 7, "product_name": "Hoodie", "view_count": 8}
                ],
                "top_promo_codes": [
                    {"promo_code_id": 5, "promo_code": "SAVE10", "used_count": 1}
                ],
                "top_banners": [
                    {"banner_id": 3, "banner_title": "Sale", "click_count": 2}
                ],
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.ADMIN)
    app.dependency_overrides[get_analytics_service] = lambda: FakeAnalyticsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/analytics/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total_orders"] == 3
    assert response.json()["order_created_count"] == 3
    assert response.json()["banner_clicked_count"] == 2
    assert response.json()["top_promo_codes"][0]["promo_code"] == "SAVE10"
    assert response.json()["top_banners"][0]["banner_title"] == "Sale"


@pytest.mark.asyncio
async def test_analytics_summary_includes_mvp_reporting_metrics() -> None:
    service = AnalyticsService(session=object())
    repository = FakeAnalyticsRepository()
    service.repository = repository

    summary = await service.get_summary(created_from=_now(), created_to=_now())

    assert summary.total_orders == 3
    assert summary.total_revenue == Decimal("179.70")
    assert summary.product_views_count == 10
    assert summary.cart_item_added_count == 4
    assert summary.checkout_started_count == 3
    assert summary.order_created_count == 3
    assert summary.promo_used_count == 1
    assert summary.banner_clicked_count == 2
    assert summary.top_products[0].product_name == "Hoodie"
    assert summary.top_promo_codes[0].promo_code == "SAVE10"
    assert summary.top_banners[0].banner_title == "Sale"


def test_normal_user_cannot_list_analytics_events() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/analytics/events")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_unauthenticated_user_cannot_list_analytics_events() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/analytics/events")

    assert response.status_code == 401


def test_seller_can_list_audit_logs() -> None:
    app = create_app()

    class FakeAuditService:
        async def list_logs(self, **_: object) -> dict[str, object]:
            return {
                "items": [
                    {
                        "id": 1,
                        "actor_user_id": 2,
                        "action": "product.updated",
                        "entity_type": "product",
                        "entity_id": 7,
                        "before_data": {"status": "DRAFT"},
                        "after_data": {"status": "ACTIVE"},
                        "metadata": None,
                        "created_at": _now().isoformat(),
                    }
                ],
                "meta": {"limit": 20, "offset": 0, "total": 1},
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.SELLER)
    app.dependency_overrides[get_audit_service] = lambda: FakeAuditService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/audit-logs?action=product.updated")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["action"] == "product.updated"


def test_seller_can_get_audit_log_detail() -> None:
    app = create_app()

    class FakeAuditService:
        async def get_log(self, log_id: int) -> dict[str, object]:
            assert log_id == 1
            return {
                "id": 1,
                "actor_user_id": 2,
                "action": "order.status_changed",
                "entity_type": "order",
                "entity_id": 9,
                "before_data": {"status": "NEW"},
                "after_data": {"status": "PROCESSING"},
                "metadata": None,
                "created_at": _now().isoformat(),
            }

    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.ADMIN)
    app.dependency_overrides[get_audit_service] = lambda: FakeAuditService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/audit-logs/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["entity_type"] == "order"


def test_normal_user_cannot_list_audit_logs() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/audit-logs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_unauthenticated_user_cannot_list_audit_logs() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/audit-logs")

    assert response.status_code == 401


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


class FakeAnalyticsRepository:
    async def count_orders(self, **_: object) -> int:
        return 3

    async def sum_order_revenue(self, **_: object) -> Decimal:
        return Decimal("179.70")

    async def count_events(self, event_name: str, **_: object) -> int:
        return {
            "product.viewed": 10,
            "cart.item_added": 4,
            "checkout.started": 3,
            "order.created": 3,
            "promo.used": 1,
            "banner.clicked": 2,
        }[event_name]

    async def top_products_by_views(self, **_: object) -> list[tuple[int, str, int]]:
        return [(7, "Hoodie", 8)]

    async def top_promo_codes_by_usage(self, **_: object) -> list[tuple[int, str, int]]:
        return [(5, "SAVE10", 1)]

    async def top_banners_by_clicks(self, **_: object) -> list[tuple[int, str, int]]:
        return [(3, "Sale", 2)]
