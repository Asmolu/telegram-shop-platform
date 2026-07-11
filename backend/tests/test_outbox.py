import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    AuditLog,
    Notification,
    NotificationChannel,
    NotificationStatus,
    OutboxDelivery,
    OutboxDeliveryStatus,
    OutboxEvent,
    OutboxStatus,
)
from app.modules.notifications.service import NotificationsService
from app.modules.outbox import worker as outbox_worker
from app.modules.outbox.repository import OutboxRepository
from app.modules.outbox.service import (
    OutboxService,
    retry_delay_seconds,
    sanitize_outbox_error,
)


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1


class CapturingOutbox:
    def __init__(self, session) -> None:
        self.session = session
        self.events: list[dict[str, object]] = []

    def enqueue(self, **values):
        self.events.append({**values, "business_committed": self.session.committed})


def _event(*, max_attempts: int = 3) -> OutboxEvent:
    return OutboxEvent(
        event_id=uuid4(),
        event_name="order.created",
        aggregate_type="order",
        aggregate_id="1",
        payload={"order_id": 1},
        status=OutboxStatus.PROCESSING,
        attempt_count=1,
        max_attempts=max_attempts,
        next_attempt_at=datetime.now(UTC),
        deliveries=[
            OutboxDelivery(
                consumer="seller", status=OutboxDeliveryStatus.PENDING, attempt_count=0
            ),
            OutboxDelivery(
                consumer="customer", status=OutboxDeliveryStatus.PENDING, attempt_count=0
            ),
        ],
    )


def test_enqueue_builds_immutable_json_safe_event_and_independent_deliveries() -> None:
    session = RecordingSession()
    event = OutboxService(session).enqueue(
        event_name="order.created",
        aggregate_type="order",
        aggregate_id=42,
        payload={"order_id": 42, "created_at": datetime(2026, 7, 11, tzinfo=UTC)},
        consumers=("seller", "customer", "seller"),
    )

    assert session.added == [event]
    assert event.event_id is not None
    assert event.aggregate_id == "42"
    assert event.payload["created_at"] == "2026-07-11T00:00:00+00:00"
    assert [delivery.consumer for delivery in event.deliveries] == ["seller", "customer"]


def test_enqueue_rejects_non_json_payload() -> None:
    with pytest.raises(ValueError):
        OutboxService(RecordingSession()).enqueue(
            event_name="bad",
            aggregate_type="order",
            aggregate_id=1,
            payload={"bad": float("nan")},
            consumers=("seller",),
        )


@pytest.mark.asyncio
async def test_seller_consumer_idempotency_reuses_sent_notification() -> None:
    now = datetime.now(UTC)
    source_event_id = uuid4()
    existing = Notification(
        id=10,
        source_event_id=source_event_id,
        source_consumer="seller",
        type="order.created",
        title="existing",
        message="existing",
        payload={"order_id": 1},
        channel=NotificationChannel.TELEGRAM,
        status=NotificationStatus.SENT,
        sent_at=now,
        created_at=now,
        updated_at=now,
    )

    class Repository:
        async def get_by_source(self, *, event_id, consumer):
            assert event_id == source_event_id
            assert consumer == "seller"
            return existing

    service = NotificationsService(RecordingSession())
    service.repository = Repository()
    result = await service.create_for_event(
        name="order.created",
        payload={"order_id": 1},
        source_event_id=source_event_id,
        source_consumer="seller",
    )
    assert result is not None
    assert result.id == existing.id
    assert result.status == NotificationStatus.SENT


@pytest.mark.asyncio
async def test_checkout_and_promo_events_are_enqueued_before_business_commit() -> None:
    from tests.test_orders import FakePromoCodesService, _checkout_payload, _orders_service

    service, _, session, _ = _orders_service(
        promo_codes_service=FakePromoCodesService()
    )
    outbox = CapturingOutbox(session)
    service.outbox_service = outbox
    await service.checkout_current_user_cart(
        user_id=1,
        payload=_checkout_payload().model_copy(update={"promo_code": "SAVE10"}),
    )
    assert [event["event_name"] for event in outbox.events] == [
        "order.created",
        "promo.used",
    ]
    assert all(event["business_committed"] is False for event in outbox.events)
    assert session.committed is True


@pytest.mark.asyncio
async def test_order_status_event_is_enqueued_before_commit() -> None:
    from app.db.models import ManualPaymentStatus, OrderStatus
    from app.modules.orders.schemas import OrderStatusUpdate
    from tests.test_orders import _checkout_payload, _orders_service

    service, repository, session, _ = _orders_service()
    outbox = CapturingOutbox(session)
    service.outbox_service = outbox
    order = await service.checkout_current_user_cart(user_id=1, payload=_checkout_payload())
    stored_order = await repository.get_by_id(order.id)
    assert stored_order is not None and stored_order.manual_payment is not None
    stored_order.manual_payment.status = ManualPaymentStatus.APPROVED
    session.committed = False
    await service.update_order_status(
        order.id,
        OrderStatusUpdate(status=OrderStatus.SHIPPED),
        actor_user_id=2,
    )
    status_events = outbox.events[1:]
    assert [event["event_name"] for event in status_events] == [
        "order.status_changed",
        "order.shipped",
    ]
    assert all(event["business_committed"] is False for event in status_events)


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(1, 5), (2, 10), (3, 20), (20, 60)],
)
def test_exponential_backoff_is_bounded(attempt: int, expected: int) -> None:
    assert retry_delay_seconds(attempt, base_seconds=5, max_seconds=60) == expected


def test_persisted_error_is_sanitized_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "secret-token")
    result = sanitize_outbox_error(RuntimeError(f"secret-token {'x' * 3000}"))
    assert "secret-token" not in result
    assert "[redacted]" in result
    assert len(result) == 2000


@pytest.mark.asyncio
async def test_successful_deliveries_finalize_event_as_processed() -> None:
    event = _event()
    for delivery in event.deliveries:
        delivery.status = OutboxDeliveryStatus.PROCESSED
    service = OutboxService(RecordingSession())
    await service._finalize_event(event)
    assert event.status == OutboxStatus.PROCESSED
    assert event.processed_at is not None
    assert event.locked_at is None


@pytest.mark.asyncio
async def test_temporary_failure_schedules_retry() -> None:
    event = _event()
    event.deliveries[0].attempt_count = 2
    event.deliveries[1].status = OutboxDeliveryStatus.PROCESSED
    before = datetime.now(UTC)
    service = OutboxService(RecordingSession())
    await service._finalize_event(event)
    assert event.status == OutboxStatus.PENDING
    assert event.next_attempt_at > before


@pytest.mark.asyncio
async def test_max_attempt_failure_and_manual_retry() -> None:
    event = _event(max_attempts=2)
    event.status = OutboxStatus.FAILED
    event.last_error = "temporary"
    event.deliveries[0].status = OutboxDeliveryStatus.FAILED
    event.deliveries[0].attempt_count = 2
    event.deliveries[1].status = OutboxDeliveryStatus.PROCESSED
    session = RecordingSession()
    service = OutboxService(session)

    class Repository:
        async def get_with_deliveries(self, event_id, *, for_update=False):
            assert event_id == event.event_id
            assert for_update is True
            return event

    service.repository = Repository()
    retried = await service.retry_failed(event.event_id)
    assert retried.status == OutboxStatus.PENDING
    assert retried.deliveries[0].status == OutboxDeliveryStatus.PENDING
    assert retried.deliveries[0].attempt_count == 0
    assert retried.deliveries[1].status == OutboxDeliveryStatus.PROCESSED
    assert session.commits == 1


@pytest.mark.asyncio
async def test_failure_increments_attempts_and_becomes_terminal_at_maximum() -> None:
    event = _event(max_attempts=2)
    delivery = event.deliveries[0]
    session = RecordingSession()
    service = OutboxService(session)

    class Repository:
        async def get_delivery(self, *, event_id, consumer, for_update=False):
            assert event_id == event.event_id
            assert consumer == "seller"
            assert for_update is True
            return event, delivery

    service.repository = Repository()
    await service.mark_delivery_failed(
        event_id=event.event_id, consumer="seller", error=RuntimeError("temporary")
    )
    assert delivery.attempt_count == 1
    assert delivery.status == OutboxDeliveryStatus.PENDING
    await service.mark_delivery_failed(
        event_id=event.event_id, consumer="seller", error=RuntimeError("still down")
    )
    assert delivery.attempt_count == 2
    assert delivery.status == OutboxDeliveryStatus.FAILED
    assert session.commits == 2


@pytest.mark.asyncio
async def test_abandoned_processing_event_is_in_claim_query() -> None:
    class CaptureSession:
        statement = None

        async def execute(self, statement):
            self.statement = statement

            class Result:
                def scalars(self):
                    return self

                def unique(self):
                    return self

                def __iter__(self):
                    return iter(())

            return Result()

    session = CaptureSession()
    now = datetime.now(UTC)
    await OutboxRepository(session).claim_due(
        now=now,
        stale_before=now - timedelta(minutes=5),
        worker_id="worker-1",
        limit=10,
    )
    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "FOR UPDATE" in sql
    assert "SKIP LOCKED" in sql
    assert "outbox_events.locked_at" in sql


@pytest.mark.asyncio
async def test_worker_isolates_consumer_failure_and_acknowledges_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    processed: list[str] = []
    failed: list[str] = []
    finished: list[object] = []

    class SessionContext:
        async def __aenter__(self):
            return RecordingSession()

        async def __aexit__(self, *args):
            return None

    class Service:
        def __init__(self, session):
            del session

        async def mark_delivery_processed(self, *, event_id, consumer):
            del event_id
            processed.append(consumer)

        async def mark_delivery_failed(self, *, event_id, consumer, error):
            del event_id, error
            failed.append(consumer)

        async def finish_attempt(self, event_id):
            finished.append(event_id)

    async def dispatch(*, event_id, event_name, payload, consumer):
        del event_id, event_name, payload
        calls.append(consumer)
        if consumer == "seller":
            raise RuntimeError("seller unavailable")

    monkeypatch.setattr(outbox_worker, "async_session_factory", SessionContext)
    monkeypatch.setattr(outbox_worker, "OutboxService", Service)
    monkeypatch.setattr(outbox_worker, "dispatch_outbox_delivery", dispatch)
    event_id = uuid4()
    await outbox_worker._process_claimed_event(
        event_id,
        "order.created",
        {"order_id": 1},
        ["seller", "customer"],
    )
    assert calls == ["seller", "customer"]
    assert failed == ["seller"]
    assert processed == ["customer"]
    assert finished == [event_id]


POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_business_and_outbox_commit_and_rollback_atomically() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        committed_event_id = uuid4()
        async with sessions() as session:
            session.add(AuditLog(action="test.commit", entity_type="test", entity_id=1))
            OutboxService(session).enqueue(
                event_id=committed_event_id,
                event_name="test.committed",
                aggregate_type="test",
                aggregate_id=1,
                payload={"entity_id": 1},
                consumers=("seller",),
            )
            await session.commit()
        rolled_back_event_id = uuid4()
        async with sessions() as session:
            session.add(AuditLog(action="test.rollback", entity_type="test", entity_id=2))
            OutboxService(session).enqueue(
                event_id=rolled_back_event_id,
                event_name="test.rolled_back",
                aggregate_type="test",
                aggregate_id=2,
                payload={"entity_id": 2},
                consumers=("seller",),
            )
            await session.rollback()
        async with sessions() as session:
            assert await session.scalar(
                select(func.count()).select_from(OutboxEvent).where(
                    OutboxEvent.event_id == committed_event_id
                )
            ) == 1
            assert await session.scalar(
                select(func.count()).select_from(OutboxEvent).where(
                    OutboxEvent.event_id == rolled_back_event_id
                )
            ) == 0
            assert await session.scalar(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == "test.commit"
                )
            ) == 1
            assert await session.scalar(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.action == "test.rollback"
                )
            ) == 0
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_skip_locked_prevents_two_workers_claiming_same_event() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    event_id = uuid4()
    try:
        async with sessions() as session:
            OutboxService(session).enqueue(
                event_id=event_id,
                event_name="order.created",
                aggregate_type="order",
                aggregate_id=1,
                payload={"order_id": 1},
                consumers=("seller",),
            )
            await session.commit()

        gate = asyncio.Event()

        async def claim(worker: str) -> list[OutboxEvent]:
            async with sessions() as session:
                rows = await OutboxRepository(session).claim_due(
                    now=datetime.now(UTC),
                    stale_before=datetime.now(UTC) - timedelta(minutes=5),
                    worker_id=worker,
                    limit=1,
                )
                gate.set()
                await asyncio.sleep(0.1)
                await session.commit()
                return rows

        first, second = await asyncio.gather(claim("one"), claim("two"))
        assert sorted((len(first), len(second))) == [0, 1]
        async with sessions() as session:
            stored = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.event_id == event_id)
            )
            assert stored is not None
            assert stored.attempt_count == 1
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()
