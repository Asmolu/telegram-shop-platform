from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.common.deps import get_optional_current_user
from app.core.config import settings
from app.core.rate_limit import reset_in_memory_rate_limiter
from app.db.models import User, UserRole
from app.main import create_app
from app.modules.analytics.router import get_analytics_service
from app.modules.analytics.schemas import TelemetryBatchIn, TelemetryIngestResult
from app.modules.analytics.service import AnalyticsService, should_keep_telemetry_event


def test_telemetry_valid_batch_accepted_without_auth() -> None:
    app = create_app()

    class FakeAnalyticsService:
        async def ingest_telemetry(self, batch, *, user_id, request_id):
            assert user_id is None
            assert request_id
            assert batch.events[0].name == "mini_app.bootstrap_started"
            return TelemetryIngestResult(accepted=1, sampled_out=0)

    app.dependency_overrides[get_analytics_service] = lambda: FakeAnalyticsService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/analytics/telemetry", json=_batch())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {"accepted": 1, "sampled_out": 0}
    assert response.headers["cache-control"] == "private, no-store"


def test_telemetry_authenticated_event_gets_server_resolved_user() -> None:
    app = create_app()
    seen: dict[str, object] = {}

    class FakeAnalyticsService:
        async def ingest_telemetry(self, batch, *, user_id, request_id):
            seen["user_id"] = user_id
            seen["request_id"] = request_id
            return TelemetryIngestResult(accepted=len(batch.events), sampled_out=0)

    app.dependency_overrides[get_optional_current_user] = lambda: _user(42)
    app.dependency_overrides[get_analytics_service] = lambda: FakeAnalyticsService()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/analytics/telemetry", json=_batch())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert seen["user_id"] == 42
    assert isinstance(seen["request_id"], str)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "unknown.event"),
        ("initData", "secret"),
        ("user_id", 7),
        ("telegram_id", 123456),
        ("endpoint_scope", "/products/123"),
        ("route", "/search?q=secret"),
        ("request_id", "x" * 65),
    ],
)
def test_telemetry_rejects_unknown_forbidden_or_excessive_fields(
    field: str,
    value: object,
) -> None:
    payload = {"events": [{**_event(), field: value}]}

    with TestClient(create_app()) as client:
        response = client.post("/api/v1/analytics/telemetry", json=payload)

    assert response.status_code == 422


def test_telemetry_rejects_excessive_events() -> None:
    payload = {"events": [_event(client_event_id=f"event-{index}") for index in range(26)]}

    with TestClient(create_app()) as client:
        response = client.post("/api/v1/analytics/telemetry", json=payload)

    assert response.status_code == 422


def test_telemetry_rejects_excessive_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telemetry_max_body_bytes", 128)

    with TestClient(create_app()) as client:
        response = client.post("/api/v1/analytics/telemetry", json=_batch())

    assert response.status_code == 413


def test_telemetry_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_in_memory_rate_limiter()
    monkeypatch.setattr(settings, "rate_limit_redis_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_telemetry_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_telemetry_window_seconds", 60)

    app = create_app()

    class FakeAnalyticsService:
        async def ingest_telemetry(self, batch, *, user_id, request_id):
            return TelemetryIngestResult(accepted=1, sampled_out=0)

    app.dependency_overrides[get_analytics_service] = lambda: FakeAnalyticsService()
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/analytics/telemetry", json=_batch())
            second = client.post("/api/v1/analytics/telemetry", json=_batch())
    finally:
        app.dependency_overrides.clear()
        reset_in_memory_rate_limiter()

    assert first.status_code == 202
    assert second.status_code == 429


def test_telemetry_sampling_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    sampled_get = TelemetryBatchIn.model_validate({
        "events": [
            {
                **_event(name="api.request_completed"),
                "method": "GET",
                "endpoint_scope": "/products",
            }
        ]
    }).events[0]
    critical = TelemetryBatchIn.model_validate({
        "events": [{**_event(name="checkout.ambiguous_outcome")}]
    }).events[0]

    monkeypatch.setattr(settings, "telemetry_success_sample_rate", 0)

    assert should_keep_telemetry_event(sampled_get) is False
    assert should_keep_telemetry_event(critical) is True


@pytest.mark.asyncio
async def test_telemetry_service_stores_request_id_and_server_timestamp() -> None:
    service = AnalyticsService(FakeSession())
    repository = FakeTelemetryRepository()
    service.repository = repository
    batch = TelemetryBatchIn.model_validate(_batch(name="api.request_failed"))

    result = await service.ingest_telemetry(batch, user_id=7, request_id="request-123")

    assert result.accepted == 1
    event = repository.events[0]
    assert event.user_id == 7
    assert event.request_id == "request-123"
    assert event.created_at.tzinfo is not None
    assert event.event_metadata == {"save_data": False, "success": False}


@pytest.mark.asyncio
async def test_telemetry_retention_cleanup_dry_run_and_delete() -> None:
    service = AnalyticsService(FakeSession())
    repository = FakeTelemetryRepository(matched=7, deleted=3)
    service.repository = repository

    dry_run = await service.cleanup_telemetry(retention_days=30, batch_size=3, dry_run=True)
    deleted = await service.cleanup_telemetry(retention_days=30, batch_size=3, dry_run=False)

    assert dry_run.matched == 7
    assert dry_run.deleted == 0
    assert deleted.deleted == 3
    assert repository.delete_limit == 3


def _batch(name: str = "mini_app.bootstrap_started") -> dict:
    return {"events": [_event(name=name)]}


def _event(
    *,
    name: str = "mini_app.bootstrap_started",
    client_event_id: str = "event-001",
) -> dict:
    return {
        "name": name,
        "version": 1,
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "client_event_id": client_event_id,
        "route": "/main",
        "platform": "android",
        "network_state": "online",
        "connection_type": "4g",
        "save_data": False,
        "success": name != "api.request_failed",
    }


def _user(user_id: int) -> User:
    return User(id=user_id, role=UserRole.USER, is_active=True)


class FakeSession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeTelemetryRepository:
    def __init__(self, *, matched: int = 0, deleted: int = 0) -> None:
        self.events = []
        self.matched = matched
        self.deleted = deleted
        self.delete_limit = 0

    def add(self, event) -> None:
        self.events.append(event)

    async def count_telemetry_before(self, cutoff: datetime) -> int:
        assert cutoff.tzinfo is not None
        return self.matched

    async def delete_telemetry_before(self, cutoff: datetime, *, limit: int) -> int:
        assert cutoff.tzinfo is not None
        self.delete_limit = limit
        return self.deleted
