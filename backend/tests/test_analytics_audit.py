from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.common.deps import get_current_user
from app.db.models import AnalyticsEvent, AuditLog, User, UserRole
from app.main import create_app
from app.modules.analytics.repository import AnalyticsRepository
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


def test_seller_can_search_analytics_events_by_query_metadata() -> None:
    app = create_app()

    class FakeAnalyticsService:
        async def list_events(self, **payload: object) -> dict[str, object]:
            assert payload["event_name"] == "search.performed"
            assert payload["search"] == "футболка"
            return {
                "items": [
                    {
                        "id": 1,
                        "event_name": "search.performed",
                        "user_id": None,
                        "product_id": None,
                        "order_id": None,
                        "promo_code_id": None,
                        "banner_id": None,
                        "metadata": {"query": "футболка", "result_count": 2},
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
                "/api/v1/analytics/events?event_name=search.performed&search=футболка"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][0]["metadata"]["query"] == "футболка"


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


@pytest.mark.parametrize("role", [UserRole.SELLER, UserRole.ADMIN])
def test_seller_or_admin_can_access_dashboard_summary(role: UserRole) -> None:
    app = create_app()

    class FakeAnalyticsService:
        async def get_dashboard_summary(self) -> dict[str, object]:
            return {
                "active_orders_count": 2,
                "active_banners_count": 1,
                "products_total": 7,
                "products_out_of_stock": 3,
                "revenue_month": {
                    "period_start": "2026-06-01T00:00:00+03:00",
                    "period_end": "2026-07-01T00:00:00+03:00",
                    "orders_count": 4,
                    "gross_revenue": "12000.00",
                    "discount_total": "1000.00",
                    "net_revenue": "11000.00",
                },
            }

    app.dependency_overrides[get_current_user] = lambda: _user(role)
    app.dependency_overrides[get_analytics_service] = lambda: FakeAnalyticsService()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/dashboard/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["active_orders_count"] == 2
    assert response.json()["active_banners_count"] == 1
    assert response.json()["products_total"] == 7
    assert response.json()["products_out_of_stock"] == 3
    assert response.json()["revenue_month"]["net_revenue"] == "11000.00"


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


@pytest.mark.asyncio
async def test_dashboard_summary_uses_current_moscow_month_interval() -> None:
    service = AnalyticsService(
        session=object(),
        now_factory=lambda: datetime(2026, 6, 18, 9, 30, tzinfo=UTC),
    )
    repository = FakeDashboardAnalyticsRepository()
    service.repository = repository

    summary = await service.get_dashboard_summary()

    assert summary.revenue_month.period_start.isoformat() == "2026-06-01T00:00:00+03:00"
    assert summary.revenue_month.period_end.isoformat() == "2026-07-01T00:00:00+03:00"
    assert repository.revenue_period == (
        summary.revenue_month.period_start,
        summary.revenue_month.period_end,
    )
    assert summary.active_orders_count == 3
    assert summary.active_banners_count == 2
    assert summary.products_total == 5
    assert summary.products_out_of_stock == 1
    assert summary.revenue_month.orders_count == 2
    assert summary.revenue_month.gross_revenue == Decimal("900.00")
    assert summary.revenue_month.discount_total == Decimal("50.00")
    assert summary.revenue_month.net_revenue == Decimal("850.00")


def test_dashboard_endpoint_rejects_normal_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.USER)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/dashboard/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_dashboard_active_order_filter_excludes_terminal_statuses() -> None:
    repository = AnalyticsRepository(session=object())

    rendered = _render_filters(repository._active_order_filters())

    assert "orders.status IN ('NEW', 'PROCESSING', 'SHIPPED')" in rendered
    assert "DELIVERED" not in rendered
    assert "CANCELLED" not in rendered


def test_dashboard_active_banner_filter_respects_status_and_date_interval() -> None:
    repository = AnalyticsRepository(session=object())

    rendered = _render_filters(repository._active_banner_filters(now=_now()))

    assert "banners.is_active IS true" in rendered
    assert "banners.target_type IS NOT NULL" in rendered
    assert "banners.starts_at IS NULL OR banners.starts_at <=" in rendered
    assert "banners.ends_at IS NULL OR banners.ends_at >" in rendered


def test_dashboard_product_filters_exclude_archived_and_detect_stockouts() -> None:
    repository = AnalyticsRepository(session=object())

    total_filter = _render_filters(repository._product_total_filters())
    out_of_stock_filter = _render_filters(repository._out_of_stock_product_filters())

    assert "products.status IN ('DRAFT', 'ACTIVE', 'OUT_OF_STOCK')" in total_filter
    assert "ARCHIVED" not in total_filter
    assert "products.status IN ('ACTIVE', 'OUT_OF_STOCK')" in out_of_stock_filter
    assert "NOT (EXISTS" in out_of_stock_filter
    assert "product_variants.is_active IS true" in out_of_stock_filter
    assert "product_variants.stock_quantity > product_variants.reserved_quantity" in (
        out_of_stock_filter
    )


def test_dashboard_revenue_filter_uses_paid_monthly_non_cancelled_orders() -> None:
    repository = AnalyticsRepository(session=object())

    rendered = _render_filters(
        repository._revenue_order_filters(
            created_from=datetime(2026, 6, 1, tzinfo=UTC),
            created_to=datetime(2026, 7, 1, tzinfo=UTC),
            end_exclusive=True,
        )
    )

    assert "orders.created_at >= '2026-06-01 00:00:00+00:00'" in rendered
    assert "orders.created_at < '2026-07-01 00:00:00+00:00'" in rendered
    assert "orders.status != 'CANCELLED'" in rendered
    assert "manual_payments.status = 'APPROVED'" in rendered
    assert "orders.status IN ('PROCESSING', 'SHIPPED', 'DELIVERED')" in rendered
    assert "PENDING" not in rendered
    assert "SUBMITTED" not in rendered
    assert "REJECTED" not in rendered
    assert "EXPIRED" not in rendered


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


class FakeDashboardAnalyticsRepository:
    def __init__(self) -> None:
        self.revenue_period: tuple[datetime, datetime] | None = None

    async def count_active_orders(self) -> int:
        return 3

    async def count_active_banners(self, **_: object) -> int:
        return 2

    async def count_products_total(self) -> int:
        return 5

    async def count_products_out_of_stock(self) -> int:
        return 1

    async def revenue_for_orders(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> tuple[int, Decimal, Decimal, Decimal]:
        self.revenue_period = (period_start, period_end)
        return (
            2,
            Decimal("900.00"),
            Decimal("50.00"),
            Decimal("850.00"),
        )


def _render_filters(filters: list[object]) -> str:
    return " ".join(
        str(
            item.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        for item in filters
    )
