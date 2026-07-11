import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
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
from app.modules.outbox.schemas import OutboxClaim
from app.modules.outbox.service import (
    OutboxService,
    retry_delay_seconds,
    sanitize_outbox_error,
)


@asynccontextmanager
async def _postgres_session_factory():
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield sessions
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _enqueue_postgres_event(
    sessions,
    *,
    consumers: tuple[str, ...] = ("seller",),
    max_attempts: int = 3,
):
    event_id = uuid4()
    async with sessions() as session:
        OutboxService(session).enqueue(
            event_id=event_id,
            event_name="order.created",
            aggregate_type="order",
            aggregate_id=1,
            payload={"order_id": 1},
            consumers=consumers,
            max_attempts=max_attempts,
        )
        await session.commit()
    return event_id


async def _claim_postgres_event(
    sessions,
    *,
    worker_id: str,
    stale_before: datetime | None = None,
) -> OutboxClaim | None:
    now = datetime.now(UTC)
    async with sessions() as session:
        claims = await OutboxRepository(session).claim_due(
            now=now,
            stale_before=stale_before or now - timedelta(minutes=5),
            worker_id=worker_id,
            limit=1,
        )
        await session.commit()
    return claims[0] if claims else None


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class CapturingOutbox:
    def __init__(self, session) -> None:
        self.session = session
        self.events: list[dict[str, object]] = []

    def enqueue(self, **values):
        self.events.append({**values, "business_committed": self.session.committed})


def _event(*, max_attempts: int = 3) -> OutboxEvent:
    return OutboxEvent(
        id=1,
        event_id=uuid4(),
        event_name="order.created",
        aggregate_type="order",
        aggregate_id="1",
        payload={"order_id": 1},
        status=OutboxStatus.PROCESSING,
        attempt_count=1,
        max_attempts=max_attempts,
        next_attempt_at=datetime.now(UTC),
        claim_token=uuid4(),
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


def test_producers_enqueue_while_worker_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "outbox_enabled", False)
    session = RecordingSession()
    event = OutboxService(session).enqueue(
        event_name="order.created",
        aggregate_type="order",
        aggregate_id=1,
        payload={"order_id": 1},
        consumers=("seller",),
    )
    assert session.added == [event]
    assert event.status == OutboxStatus.PENDING


@pytest.mark.asyncio
async def test_worker_loop_survives_visible_cycle_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    stop_event = asyncio.Event()
    calls = 0

    async def process(*, worker_id):
        nonlocal calls
        del worker_id
        calls += 1
        if calls == 1:
            raise RuntimeError("database unavailable")
        stop_event.set()
        return 0

    monkeypatch.setattr(settings, "outbox_poll_interval_seconds", 0.001)
    monkeypatch.setattr(outbox_worker, "process_outbox_batch", process)
    await asyncio.wait_for(outbox_worker.run_outbox_worker(stop_event), timeout=1)
    assert calls == 2


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


def test_heartbeat_interval_is_one_third_of_lease_timeout() -> None:
    interval = outbox_worker.heartbeat_interval_seconds(300)
    assert interval == 100
    assert 0 < interval < 300 / 2


@pytest.mark.asyncio
async def test_lost_heartbeat_ownership_prevents_delivery_and_final_acknowledgements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched = False
    finished = False

    async def heartbeat(claim, *, worker_id, stop_event, ownership_lost):
        del claim, worker_id, stop_event
        ownership_lost.set()

    async def dispatch(**kwargs):
        nonlocal dispatched
        del kwargs
        dispatched = True
        await asyncio.sleep(0)

    class Service:
        def __init__(self, session):
            del session

        async def finish_attempt(self, **kwargs):
            nonlocal finished
            del kwargs
            finished = True

    monkeypatch.setattr(outbox_worker, "_heartbeat_claim", heartbeat)
    monkeypatch.setattr(outbox_worker, "dispatch_outbox_delivery", dispatch)
    monkeypatch.setattr(outbox_worker, "OutboxService", Service)
    claim = OutboxClaim.create(
        database_id=1,
        event_id=uuid4(),
        claim_token=uuid4(),
        event_name="order.created",
        payload={"order_id": 1},
        pending_consumers=("seller",),
    )
    await outbox_worker._process_claimed_event(claim, worker_id="worker")
    assert dispatched
    assert not finished


@pytest.mark.asyncio
async def test_heartbeat_cancellation_does_not_leak_task() -> None:
    stop_event = asyncio.Event()
    ownership_lost = asyncio.Event()
    claim = OutboxClaim.create(
        database_id=1,
        event_id=uuid4(),
        claim_token=uuid4(),
        event_name="order.created",
        payload={"order_id": 1},
        pending_consumers=("seller",),
    )
    task = asyncio.create_task(
        outbox_worker._heartbeat_claim(
            claim,
            worker_id="worker",
            stop_event=stop_event,
            ownership_lost=ownership_lost,
        )
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.done()


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
        async def get_owned_with_deliveries(
            self, *, event_database_id, claim_token, for_update=False
        ):
            assert event_database_id == event.id
            assert for_update is True
            return event if claim_token == event.claim_token else None

    service.repository = Repository()
    first_token = event.claim_token
    assert first_token is not None
    await service.mark_delivery_failed(
        event_database_id=event.id,
        event_id=event.event_id,
        claim_token=first_token,
        consumer="seller",
        error=RuntimeError("temporary"),
    )
    assert delivery.attempt_count == 1
    assert delivery.status == OutboxDeliveryStatus.PENDING
    await service.mark_delivery_failed(
        event_database_id=event.id,
        event_id=event.event_id,
        claim_token=first_token,
        consumer="seller",
        error=RuntimeError("duplicate"),
    )
    assert delivery.attempt_count == 1
    event.claim_token = uuid4()
    await service.mark_delivery_failed(
        event_database_id=event.id,
        event_id=event.event_id,
        claim_token=event.claim_token,
        consumer="seller",
        error=RuntimeError("still down"),
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

        async def mark_delivery_processed(self, **kwargs):
            consumer = kwargs["consumer"]
            processed.append(consumer)
            return True

        async def mark_delivery_failed(self, **kwargs):
            consumer = kwargs["consumer"]
            failed.append(consumer)
            return True

        async def finish_attempt(self, **kwargs):
            finished.append(kwargs["event_id"])
            return True

    async def dispatch(*, event_id, event_name, payload, consumer):
        del event_id, event_name, payload
        calls.append(consumer)
        if consumer == "seller":
            raise RuntimeError("seller unavailable")

    monkeypatch.setattr(outbox_worker, "async_session_factory", SessionContext)
    monkeypatch.setattr(outbox_worker, "OutboxService", Service)
    monkeypatch.setattr(outbox_worker, "dispatch_outbox_delivery", dispatch)
    async def heartbeat(*args, **kwargs):
        del args, kwargs

    monkeypatch.setattr(outbox_worker, "_heartbeat_claim", heartbeat)
    event_id = uuid4()
    claim = OutboxClaim.create(
        database_id=1,
        event_id=event_id,
        claim_token=uuid4(),
        event_name="order.created",
        payload={"order_id": 1},
        pending_consumers=("seller", "customer"),
    )
    await outbox_worker._process_claimed_event(
        claim,
        worker_id="worker-test",
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


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_late_failure_cannot_regress_newer_success() -> None:
    async with _postgres_session_factory() as sessions:
        event_id = await _enqueue_postgres_event(sessions, max_attempts=1)
        claim_a = await _claim_postgres_event(sessions, worker_id="reused-worker")
        assert claim_a is not None
        async with sessions() as session:
            await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == claim_a.database_id)
                .values(locked_at=datetime.now(UTC) - timedelta(minutes=10))
            )
            await session.commit()

        claim_b = await _claim_postgres_event(sessions, worker_id="reused-worker")
        assert claim_b is not None
        assert claim_b.claim_token != claim_a.claim_token
        async with sessions() as session:
            service = OutboxService(session)
            assert await service.mark_delivery_processed(
                event_database_id=claim_b.database_id,
                event_id=claim_b.event_id,
                claim_token=claim_b.claim_token,
                consumer="seller",
            )
            assert await service.finish_attempt(
                event_database_id=claim_b.database_id,
                event_id=claim_b.event_id,
                claim_token=claim_b.claim_token,
            )

        async with sessions() as session:
            service = OutboxService(session)
            assert not await service.mark_delivery_failed(
                event_database_id=claim_a.database_id,
                event_id=claim_a.event_id,
                claim_token=claim_a.claim_token,
                consumer="seller",
                error=RuntimeError("late worker failure"),
            )

        async with sessions() as session:
            event = await OutboxRepository(session).get_with_deliveries(event_id)
            assert event is not None
            assert event.status == OutboxStatus.PROCESSED
            assert event.claim_token is None
            assert event.deliveries[0].status == OutboxDeliveryStatus.PROCESSED
            assert event.deliveries[0].attempt_count == 0
            assert event.next_attempt_at is not None


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_claim_fencing_and_stale_recovery_rules() -> None:
    async with _postgres_session_factory() as sessions:
        await _enqueue_postgres_event(sessions)
        claim_a = await _claim_postgres_event(sessions, worker_id="same-id")
        assert claim_a is not None
        assert claim_a.claim_token.version == 4

        assert await _claim_postgres_event(sessions, worker_id="same-id") is None
        async with sessions() as session:
            await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == claim_a.database_id)
                .values(locked_at=datetime.now(UTC) - timedelta(minutes=10))
            )
            await session.commit()
        claim_b = await _claim_postgres_event(sessions, worker_id="same-id")
        assert claim_b is not None
        assert claim_b.claim_token != claim_a.claim_token

        async with sessions() as session:
            service = OutboxService(session)
            assert not await service.renew_claim(
                event_database_id=claim_a.database_id,
                event_id=claim_a.event_id,
                claim_token=claim_a.claim_token,
            )
            assert await service.renew_claim(
                event_database_id=claim_b.database_id,
                event_id=claim_b.event_id,
                claim_token=claim_b.claim_token,
            )
        assert await _claim_postgres_event(sessions, worker_id="other") is None


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_duplicate_acknowledgements_are_idempotent() -> None:
    async with _postgres_session_factory() as sessions:
        event_id = await _enqueue_postgres_event(sessions, max_attempts=2)
        claim = await _claim_postgres_event(sessions, worker_id="one")
        assert claim is not None
        async with sessions() as session:
            service = OutboxService(session)
            for error in (RuntimeError("first"), RuntimeError("duplicate")):
                assert await service.mark_delivery_failed(
                    event_database_id=claim.database_id,
                    event_id=claim.event_id,
                    claim_token=claim.claim_token,
                    consumer="seller",
                    error=error,
                )
            event = await OutboxRepository(session).get_with_deliveries(event_id)
            assert event is not None
            assert event.deliveries[0].attempt_count == 1
            assert await service.finish_attempt(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
            )
            assert not await service.mark_delivery_failed(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
                consumer="seller",
                error=RuntimeError("finished duplicate"),
            )

        async with sessions() as session:
            await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.event_id == event_id)
                .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
        second_claim = await _claim_postgres_event(sessions, worker_id="two")
        assert second_claim is not None
        async with sessions() as session:
            service = OutboxService(session)
            assert await service.mark_delivery_processed(
                event_database_id=second_claim.database_id,
                event_id=second_claim.event_id,
                claim_token=second_claim.claim_token,
                consumer="seller",
            )
            assert await service.mark_delivery_processed(
                event_database_id=second_claim.database_id,
                event_id=second_claim.event_id,
                claim_token=second_claim.claim_token,
                consumer="seller",
            )
            assert await service.finish_attempt(
                event_database_id=second_claim.database_id,
                event_id=second_claim.event_id,
                claim_token=second_claim.claim_token,
            )
            assert not await service.mark_delivery_processed(
                event_database_id=second_claim.database_id,
                event_id=second_claim.event_id,
                claim_token=second_claim.claim_token,
                consumer="seller",
            )


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_late_success_cannot_overwrite_newer_terminal_failure() -> None:
    async with _postgres_session_factory() as sessions:
        event_id = await _enqueue_postgres_event(sessions, max_attempts=1)
        claim_a = await _claim_postgres_event(sessions, worker_id="a")
        assert claim_a is not None
        async with sessions() as session:
            await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == claim_a.database_id)
                .values(locked_at=datetime.now(UTC) - timedelta(minutes=10))
            )
            await session.commit()
        claim_b = await _claim_postgres_event(sessions, worker_id="b")
        assert claim_b is not None
        async with sessions() as session:
            service = OutboxService(session)
            assert await service.mark_delivery_failed(
                event_database_id=claim_b.database_id,
                event_id=claim_b.event_id,
                claim_token=claim_b.claim_token,
                consumer="seller",
                error=RuntimeError("terminal"),
            )
            assert await service.finish_attempt(
                event_database_id=claim_b.database_id,
                event_id=claim_b.event_id,
                claim_token=claim_b.claim_token,
            )
        async with sessions() as session:
            service = OutboxService(session)
            assert not await service.mark_delivery_processed(
                event_database_id=claim_a.database_id,
                event_id=claim_a.event_id,
                claim_token=claim_a.claim_token,
                consumer="seller",
            )
            event = await OutboxRepository(session).get_with_deliveries(event_id)
            assert event is not None
            assert event.status == OutboxStatus.FAILED
            assert event.deliveries[0].status == OutboxDeliveryStatus.FAILED


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.parametrize("successful_consumer", ["seller", "customer"])
@pytest.mark.asyncio
async def test_postgres_multi_consumer_failure_isolation_and_retry(
    successful_consumer: str,
) -> None:
    failed_consumer = "customer" if successful_consumer == "seller" else "seller"
    async with _postgres_session_factory() as sessions:
        event_id = await _enqueue_postgres_event(
            sessions, consumers=("seller", "customer"), max_attempts=2
        )
        claim = await _claim_postgres_event(sessions, worker_id="one")
        assert claim is not None
        async with sessions() as session:
            service = OutboxService(session)
            assert await service.mark_delivery_processed(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
                consumer=successful_consumer,
            )
            assert await service.mark_delivery_failed(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
                consumer=failed_consumer,
                error=RuntimeError("temporary"),
            )
            assert await service.finish_attempt(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
            )
        async with sessions() as session:
            event = await OutboxRepository(session).get_with_deliveries(event_id)
            assert event is not None
            statuses = {delivery.consumer: delivery.status for delivery in event.deliveries}
            assert statuses[successful_consumer] == OutboxDeliveryStatus.PROCESSED
            assert statuses[failed_consumer] == OutboxDeliveryStatus.PENDING
            event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()
        retry_claim = await _claim_postgres_event(sessions, worker_id="two")
        assert retry_claim is not None
        assert retry_claim.pending_consumers == (failed_consumer,)
        async with sessions() as session:
            service = OutboxService(session)
            assert await service.mark_delivery_processed(
                event_database_id=retry_claim.database_id,
                event_id=retry_claim.event_id,
                claim_token=retry_claim.claim_token,
                consumer=failed_consumer,
            )
            assert await service.finish_attempt(
                event_database_id=retry_claim.database_id,
                event_id=retry_claim.event_id,
                claim_token=retry_claim.claim_token,
            )
            event = await OutboxRepository(session).get_with_deliveries(event_id)
            assert event is not None
            assert event.status == OutboxStatus.PROCESSED


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_manual_retry_is_serialized_and_preserves_success() -> None:
    from app.core.errors import AppError

    async with _postgres_session_factory() as sessions:
        event_id = await _enqueue_postgres_event(
            sessions, consumers=("seller", "customer"), max_attempts=1
        )
        claim = await _claim_postgres_event(sessions, worker_id="worker")
        assert claim is not None
        async with sessions() as session:
            service = OutboxService(session)
            assert await service.mark_delivery_processed(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
                consumer="seller",
            )
            assert await service.mark_delivery_failed(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
                consumer="customer",
                error=RuntimeError("terminal"),
            )
            assert await service.finish_attempt(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
            )

        async def retry_once():
            async with sessions() as session:
                return await OutboxService(session).retry_failed(event_id)

        results = await asyncio.gather(retry_once(), retry_once(), return_exceptions=True)
        assert sum(not isinstance(result, BaseException) for result in results) == 1
        assert sum(isinstance(result, AppError) for result in results) == 1
        async with sessions() as session:
            event = await OutboxRepository(session).get_with_deliveries(event_id)
            assert event is not None
            statuses = {delivery.consumer: delivery.status for delivery in event.deliveries}
            assert event.status == OutboxStatus.PENDING
            assert statuses == {
                "seller": OutboxDeliveryStatus.PROCESSED,
                "customer": OutboxDeliveryStatus.PENDING,
            }


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_active_claim_cannot_be_manually_retried() -> None:
    from app.core.errors import AppError

    async with _postgres_session_factory() as sessions:
        event_id = await _enqueue_postgres_event(sessions)
        claim = await _claim_postgres_event(sessions, worker_id="active")
        assert claim is not None

        async def acknowledge_current_claim():
            async with sessions() as session:
                return await OutboxService(session).mark_delivery_processed(
                    event_database_id=claim.database_id,
                    event_id=claim.event_id,
                    claim_token=claim.claim_token,
                    consumer="seller",
                )

        async def retry_active_claim():
            async with sessions() as session:
                return await OutboxService(session).retry_failed(event_id)

        acknowledged, retry_result = await asyncio.gather(
            acknowledge_current_claim(), retry_active_claim(), return_exceptions=True
        )
        assert acknowledged is True
        assert isinstance(retry_result, AppError)
        async with sessions() as session:
            event = await OutboxRepository(session).get_with_deliveries(event_id)
            assert event is not None
            assert event.status == OutboxStatus.PROCESSING
            assert event.claim_token == claim.claim_token
            assert event.deliveries[0].status == OutboxDeliveryStatus.PROCESSED
            assert await OutboxService(session).finish_attempt(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
            )


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_manual_payment_configuration_failure_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings
    from app.events.names import MANUAL_PAYMENT_SUBMITTED
    from app.modules.manual_payments.service import ManualPaymentEventPublisher
    from app.modules.telegram.service import TelegramDeliveryError

    monkeypatch.setattr(settings, "telegram_bot_token", None)
    monkeypatch.setattr(settings, "telegram_orders_chat_id", None)
    monkeypatch.setattr(settings, "telegram_seller_chat_id", None)
    payload = {
        "payment_id": 999,
        "order_id": 1,
        "order_number": "ORD-1",
        "user_id": 1,
        "customer_username": "customer",
        "customer_phone": "+70000000000",
        "delivery_method_label": "Delivery",
        "amount": "100.00",
        "payment_comment": "test",
        "expires_at": datetime.now(UTC).isoformat(),
        "has_receipt": False,
        "receipt_image_path": None,
        "status": "SUBMITTED",
    }

    class MissingTelegram:
        bot_token = None
        seller_chat_id = None

    class ConfiguredTelegram:
        bot_token = "configured-for-test"
        seller_chat_id = "-100-test"
        sent = 0

        async def send_message(self, chat_id, message, **kwargs):
            del chat_id, message, kwargs
            self.sent += 1
            return 123

    async with _postgres_session_factory() as sessions:
        event_id = uuid4()
        async with sessions() as session:
            OutboxService(session).enqueue(
                event_id=event_id,
                event_name=MANUAL_PAYMENT_SUBMITTED,
                aggregate_type="manual_payment",
                aggregate_id=999,
                payload=payload,
                consumers=("seller",),
                max_attempts=1,
            )
            await session.commit()
        claim = await _claim_postgres_event(sessions, worker_id="missing-config")
        assert claim is not None
        async with sessions() as session:
            with pytest.raises(TelegramDeliveryError) as error:
                await ManualPaymentEventPublisher(
                    session, telegram_service=MissingTelegram()
                ).emit_seller(MANUAL_PAYMENT_SUBMITTED, payload)
            service = OutboxService(session)
            assert await service.mark_delivery_failed(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
                consumer="seller",
                error=error.value,
            )
            assert await service.finish_attempt(
                event_database_id=claim.database_id,
                event_id=claim.event_id,
                claim_token=claim.claim_token,
            )
            failed = await OutboxRepository(session).get_with_deliveries(event_id)
            assert failed is not None
            assert failed.status == OutboxStatus.FAILED
            assert "configured-for-test" not in (failed.last_error or "")

        async with sessions() as session:
            await OutboxService(session).retry_failed(event_id)
        retry_claim = await _claim_postgres_event(sessions, worker_id="fixed-config")
        assert retry_claim is not None
        telegram = ConfiguredTelegram()
        async with sessions() as session:
            await ManualPaymentEventPublisher(
                session, telegram_service=telegram
            ).emit_seller(MANUAL_PAYMENT_SUBMITTED, payload)
            service = OutboxService(session)
            assert await service.mark_delivery_processed(
                event_database_id=retry_claim.database_id,
                event_id=retry_claim.event_id,
                claim_token=retry_claim.claim_token,
                consumer="seller",
            )
            assert await service.finish_attempt(
                event_database_id=retry_claim.database_id,
                event_id=retry_claim.event_id,
                claim_token=retry_claim.claim_token,
            )
            processed = await OutboxRepository(session).get_with_deliveries(event_id)
            assert processed is not None
            assert processed.status == OutboxStatus.PROCESSED
            assert telegram.sent == 1
