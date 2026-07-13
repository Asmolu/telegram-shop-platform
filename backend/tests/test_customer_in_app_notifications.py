import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import AppError
from app.db.base import Base
from app.db.models import (
    AuditLog,
    CustomerInAppNotification,
    CustomerInAppNotificationActionMode,
    CustomerInAppNotificationCategory,
    CustomerInAppNotificationVariant,
    IdempotencyRecord,
    ManualPayment,
    ManualPaymentCurrency,
    ManualPaymentMethod,
    ManualPaymentStatus,
    Order,
    OrderDeliveryMethod,
    OrderStatus,
    OutboxEvent,
    ReturnRequestStatus,
    User,
)
from app.events.names import MANUAL_PAYMENT_SUBMITTED
from app.modules.audit.service import AuditService
from app.modules.customer_in_app_notifications.service import CustomerInAppNotificationsService
from app.modules.manual_payments.service import ManualPaymentsService
from app.modules.orders.schemas import OrderStatusUpdate
from app.modules.orders.service import OrdersService
from app.modules.outbox.service import OutboxService

NOW = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")


class Result:
    def scalar_one_or_none(self):
        return None


class CaptureSession:
    def __init__(self) -> None:
        self.added = []

    def add(self, item) -> None:
        self.added.append(item)

    async def execute(self, _statement):
        return Result()


class FixedEventOutboxService:
    def __init__(self, session, event_id: UUID) -> None:
        self.delegate = OutboxService(session)
        self.event_id = event_id

    def enqueue(self, **kwargs):
        if kwargs["event_name"] == "order.status_changed":
            kwargs["event_id"] = self.event_id
        return self.delegate.enqueue(**kwargs)


def order(*, status: OrderStatus = OrderStatus.NEW):
    return SimpleNamespace(
        id=10,
        user_id=7,
        order_number="ORD-000010",
        status=status,
        total_amount=Decimal("7262.00"),
        delivery_method=OrderDeliveryMethod.CDEK,
        created_at=NOW,
    )


@pytest.mark.asyncio
async def test_initial_payment_and_return_statuses_create_no_notifications() -> None:
    session = CaptureSession()
    service = CustomerInAppNotificationsService(session)
    new_order = order()
    payment = SimpleNamespace(
        id=20,
        order_id=10,
        order=new_order,
        status=ManualPaymentStatus.PENDING,
    )
    return_request = SimpleNamespace(
        id=30,
        order_id=10,
        user_id=7,
        return_number="RET-000030",
        status=ReturnRequestStatus.PENDING,
    )

    await service.create_payment_status(payment, occurred_at=NOW)
    await service.create_return_status(return_request, occurred_at=NOW)

    assert session.added == []


@pytest.mark.asyncio
async def test_status_notifications_capture_immutable_copy_and_stable_source_keys() -> None:
    session = CaptureSession()
    service = CustomerInAppNotificationsService(session)
    changed_order = order(status=OrderStatus.PROCESSING)
    payment = SimpleNamespace(
        id=20,
        order_id=10,
        order=changed_order,
        status=ManualPaymentStatus.APPROVED,
    )
    return_request = SimpleNamespace(
        id=30,
        order_id=10,
        user_id=7,
        return_number="RET-000030",
        status=ReturnRequestStatus.REJECTED,
    )

    await service.create_order_status(
        changed_order,
        occurred_at=NOW,
        source_key="order:10:PROCESSING:outbox:test-occurrence",
    )
    await service.create_payment_status(payment, occurred_at=NOW)
    await service.create_return_status(return_request, occurred_at=NOW)

    order_notification, payment_notification, return_notification = session.added
    assert order_notification.source_key == "order:10:PROCESSING:outbox:test-occurrence"
    assert order_notification.action_mode == CustomerInAppNotificationActionMode.CONTINUE_ONLY
    assert order_notification.payload["order_number"] == "ORD-000010"
    assert payment_notification.source_key == "payment:20:APPROVED"
    assert payment_notification.variant == CustomerInAppNotificationVariant.APPROVED_PAYMENT
    assert payment_notification.payload["total_amount"] == "7262.00"
    assert return_notification.source_key == "return:30:REJECTED"
    assert (
        return_notification.action_mode
        == CustomerInAppNotificationActionMode.CONTINUE_WITH_CONTACTS
    )


@pytest.mark.asyncio
async def test_order_source_key_accepts_persisted_transition_occurrence() -> None:
    session = CaptureSession()
    service = CustomerInAppNotificationsService(session)
    changed_order = order(status=OrderStatus.PROCESSING)

    await service.create_order_status(
        changed_order,
        occurred_at=NOW,
        source_key="order:10:PROCESSING:outbox:00000000-0000-0000-0000-000000000056",
    )

    assert session.added[0].source_key.endswith(":00000000-0000-0000-0000-000000000056")


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_pending_seen_ownership_and_ordering() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id.in_((99005601, 99005602))))
            first_user = User(telegram_id=99005601)
            second_user = User(telegram_id=99005602)
            session.add_all((first_user, second_user))
            await session.flush()
            session.add_all(
                (
                    _db_notification(first_user.id, "test:order:later", NOW.replace(hour=11)),
                    _db_notification(first_user.id, "test:order:first", NOW),
                    _db_notification(second_user.id, "test:other-user", NOW),
                )
            )
            await session.commit()

        async with sessions() as session:
            service = CustomerInAppNotificationsService(session)
            pending = await service.pending(user_id=first_user.id, limit=20)
            assert [item.message for item in pending] == ["test:order:first", "test:order:later"]
            seen = await service.mark_seen(notification_id=pending[0].id, user_id=first_user.id)
            assert seen.seen_at is not None
            remaining = await service.pending(user_id=first_user.id, limit=20)
            assert [item.message for item in remaining] == ["test:order:later"]

        async with sessions() as session:
            service = CustomerInAppNotificationsService(session)
            with pytest.raises(AppError, match="Notification not found"):
                await service.mark_seen(notification_id=pending[0].id, user_id=second_user.id)
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id.in_((99005601, 99005602))))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_unique_source_key_fences_concurrent_duplicates() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        await session.execute(delete(User).where(User.telegram_id == 99005603))
        user = User(telegram_id=99005603)
        session.add(user)
        await session.commit()
        user_id = user.id

    async def insert_once() -> bool:
        async with sessions() as session:
            session.add(_db_notification(user_id, "test:concurrent", NOW))
            try:
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False

    try:
        results = await asyncio.gather(insert_once(), insert_once())
        assert sorted(results) == [False, True]
        async with sessions() as session:
            rows = await session.execute(
                select(CustomerInAppNotification).where(
                    CustomerInAppNotification.source_key == "test:concurrent"
                )
            )
            assert len(list(rows.scalars())) == 1
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == 99005603))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_duplicate_notification_preserves_order_audit_outbox_and_session() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    event_id = UUID("00000000-0000-0000-0000-000000000056")
    telegram_id = 99005604
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(OutboxEvent).where(OutboxEvent.event_id == event_id))
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()
            db_order = _db_order(user.id, "ORD-99005604")
            session.add(db_order)
            await session.flush()
            source_key = f"order:{db_order.id}:PROCESSING:outbox:{event_id}"
            notification = _db_notification(user.id, source_key, NOW)
            notification.order_id = db_order.id
            session.add(notification)
            await session.commit()
            order_id = db_order.id

        async with sessions() as session:
            service = OrdersService(session, audit_service=AuditService(session))
            service.outbox_service = FixedEventOutboxService(session, event_id)
            await service.update_order_status(
                order_id,
                OrderStatusUpdate(status=OrderStatus.PROCESSING),
                actor_user_id=None,
            )

            assert await session.scalar(select(Order.status).where(Order.id == order_id)) == (
                OrderStatus.PROCESSING
            )
            assert await session.scalar(
                select(CustomerInAppNotification.id).where(
                    CustomerInAppNotification.source_key == source_key
                )
            )
            assert await session.scalar(
                select(AuditLog.id).where(
                    AuditLog.action == "order.status_changed",
                    AuditLog.entity_id == order_id,
                )
            )
            assert await session.scalar(
                select(OutboxEvent.id).where(OutboxEvent.event_id == event_id)
            )
            # A query after the suppressed conflict proves the session is not failed.
            assert await session.scalar(select(User.id).where(User.id == user.id)) == user.id
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_unrelated_notification_integrity_error_aborts_transition() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    telegram_id = 99005605
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()
            db_order = _db_order(user.id, "ORD-99005605")
            session.add(db_order)
            await session.commit()
            order_id = db_order.id

        async with sessions() as session:
            service = OrdersService(session, audit_service=AuditService(session))
            real_notifications = CustomerInAppNotificationsService(session)

            async def insert_invalid_notification(*_args, **_kwargs):
                await real_notifications.repository.insert_if_source_absent(
                    _db_notification(2_147_483_647, "test:invalid-foreign-key", NOW)
                )

            service.in_app_notifications.create_order_status = insert_invalid_notification
            with pytest.raises(IntegrityError):
                await service.update_order_status(
                    order_id,
                    OrderStatusUpdate(status=OrderStatus.PROCESSING),
                    actor_user_id=None,
                )
            await session.rollback()

        async with sessions() as session:
            assert await session.scalar(select(Order.status).where(Order.id == order_id)) == (
                OrderStatus.NEW
            )
            assert (
                await session.scalar(
                    select(CustomerInAppNotification.id).where(
                        CustomerInAppNotification.source_key == "test:invalid-foreign-key"
                    )
                )
                is None
            )
            assert (
                await session.scalar(
                    select(AuditLog.id).where(
                        AuditLog.action == "order.status_changed",
                        AuditLog.entity_id == order_id,
                    )
                )
                is None
            )
            assert (
                await session.scalar(
                    select(OutboxEvent.id).where(OutboxEvent.aggregate_id == str(order_id))
                )
                is None
            )
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_order_reentry_creates_distinct_occurrence_notifications() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    telegram_id = 99005606
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()
            db_order = _db_order(user.id, "ORD-99005606")
            session.add(db_order)
            await session.commit()
            order_id = db_order.id

        async with sessions() as session:
            service = OrdersService(session)
            await service.update_order_status(
                order_id, OrderStatusUpdate(status=OrderStatus.PROCESSING)
            )
            await service.update_order_status(order_id, OrderStatusUpdate(status=OrderStatus.NEW))
            await service.update_order_status(
                order_id, OrderStatusUpdate(status=OrderStatus.PROCESSING)
            )

        async with sessions() as session:
            keys = list(
                (
                    await session.scalars(
                        select(CustomerInAppNotification.source_key).where(
                            CustomerInAppNotification.order_id == order_id,
                            CustomerInAppNotification.event_code == "PROCESSING",
                        )
                    )
                ).all()
            )
            assert len(keys) == 2
            assert len(set(keys)) == 2
            assert all(":outbox:" in key for key in keys)
            assert await session.scalar(
                select(func.count(CustomerInAppNotification.id)).where(
                    CustomerInAppNotification.order_id == order_id,
                    CustomerInAppNotification.event_code == "NEW",
                )
            ) == 1
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_concurrent_order_transition_creates_one_occurrence() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    telegram_id = 99005608
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()
            db_order = _db_order(user.id, "ORD-99005608")
            session.add(db_order)
            await session.commit()
            order_id = db_order.id

        async def transition_once():
            async with sessions() as session:
                return await OrdersService(session).update_order_status(
                    order_id, OrderStatusUpdate(status=OrderStatus.PROCESSING)
                )

        first, second = await asyncio.gather(transition_once(), transition_once())
        assert first.status == second.status == OrderStatus.PROCESSING
        async with sessions() as session:
            notification_count = await session.scalar(
                select(func.count(CustomerInAppNotification.id)).where(
                    CustomerInAppNotification.order_id == order_id,
                    CustomerInAppNotification.event_code == "PROCESSING",
                )
            )
            event_count = await session.scalar(
                select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.aggregate_id == str(order_id),
                    OutboxEvent.event_name == "order.status_changed",
                )
            )
            assert notification_count == 1
            assert event_count == 1
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_new_approved_payment_creates_one_transactional_notification() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    telegram_id = 99005609
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()
            db_order = _db_order(user.id, "ORD-99005609")
            session.add(db_order)
            await session.flush()
            payment = ManualPayment(
                order_id=db_order.id,
                method=ManualPaymentMethod.SBP_PHONE,
                amount=db_order.total_amount,
                currency=ManualPaymentCurrency.RUB,
                seller_phone_e164="+79990000000",
                seller_phone_display="+7 999 000-00-00",
                payment_comment="ORD-99005609",
                status=ManualPaymentStatus.PENDING,
                expires_at=NOW.replace(day=14),
            )
            session.add(payment)
            await session.commit()
            payment_id = payment.id
            order_id = db_order.id

        async with sessions() as session:
            service = ManualPaymentsService(session)
            first = await service.approve(payment_id, actor_user_id=None)
            second = await service.approve(payment_id, actor_user_id=None)
            assert first.status == second.status == ManualPaymentStatus.APPROVED

        async with sessions() as session:
            assert await session.scalar(
                select(func.count(CustomerInAppNotification.id)).where(
                    CustomerInAppNotification.source_key == f"payment:{payment_id}:APPROVED"
                )
            ) == 1
            assert await session.scalar(
                select(func.count(CustomerInAppNotification.id)).where(
                    CustomerInAppNotification.order_id == order_id,
                    CustomerInAppNotification.category
                    == CustomerInAppNotificationCategory.ORDER,
                    CustomerInAppNotification.event_code == "PROCESSING",
                )
            ) == 1
            assert await session.scalar(select(Order.status).where(Order.id == order_id)) == (
                OrderStatus.PROCESSING
            )
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.parametrize(
    ("telegram_id", "order_number", "receipt_image_path"),
    (
        (99005610, "ORD-99005610", "payment_receipts/keep.png"),
        (99005611, "ORD-99005611", None),
    ),
)
@pytest.mark.asyncio
async def test_postgres_manual_payment_submission_serializes_persisted_timestamp_once(
    telegram_id: int,
    order_number: str,
    receipt_image_path: str | None,
) -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    payment_id: int | None = None
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()
            db_order = _db_order(user.id, order_number)
            session.add(db_order)
            await session.flush()
            payment = ManualPayment(
                order_id=db_order.id,
                method=ManualPaymentMethod.SBP_PHONE,
                amount=db_order.total_amount,
                currency=ManualPaymentCurrency.RUB,
                seller_phone_e164="+79990000000",
                seller_phone_display="+7 999 000-00-00",
                payment_comment=order_number,
                status=ManualPaymentStatus.PENDING,
                receipt_image_path=receipt_image_path,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            session.add(payment)
            await session.commit()
            payment_id = payment.id
            order_id = db_order.id
            user_id = user.id

        idempotency_key = f"payment-submit-{telegram_id}"
        async with sessions() as session:
            service = ManualPaymentsService(session)
            first = await service.submit(
                order_id=order_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
            )
            replayed = await service.submit(
                order_id=order_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
            )
            repeated = await service.submit(order_id=order_id, user_id=user_id)

        assert first.status == ManualPaymentStatus.SUBMITTED
        assert first.submitted_at is not None
        assert first.updated_at is not None
        assert first.receipt_image_path == receipt_image_path
        assert replayed == first
        assert repeated.submitted_at == first.submitted_at
        assert repeated.updated_at == first.updated_at

        async with sessions() as session:
            stored = await session.get(ManualPayment, payment_id)
            assert stored is not None
            assert stored.status == ManualPaymentStatus.SUBMITTED
            assert stored.submitted_at == first.submitted_at
            assert stored.updated_at == first.updated_at
            assert stored.receipt_image_path == receipt_image_path
            assert await session.scalar(
                select(func.count(CustomerInAppNotification.id)).where(
                    CustomerInAppNotification.source_key
                    == f"payment:{payment_id}:SUBMITTED"
                )
            ) == 1
            assert await session.scalar(
                select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.aggregate_type == "manual_payment",
                    OutboxEvent.aggregate_id == str(payment_id),
                    OutboxEvent.event_name == MANUAL_PAYMENT_SUBMITTED,
                )
            ) == 1
            idempotency = await session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.user_id == user_id,
                    IdempotencyRecord.scope == "manual_payments.submit",
                    IdempotencyRecord.key == idempotency_key,
                )
            )
            assert idempotency is not None
            assert idempotency.status == "SUCCEEDED"
            assert idempotency.response_body == first.model_dump(mode="json")
    finally:
        async with sessions() as session:
            if payment_id is not None:
                await session.execute(
                    delete(OutboxEvent).where(
                        OutboxEvent.aggregate_type == "manual_payment",
                        OutboxEvent.aggregate_id == str(payment_id),
                    )
                )
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_manual_payment_submission_commit_failure_rolls_back_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    telegram_id = 99005612
    payment_id: int | None = None
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()
            db_order = _db_order(user.id, "ORD-99005612")
            session.add(db_order)
            await session.flush()
            payment = ManualPayment(
                order_id=db_order.id,
                method=ManualPaymentMethod.SBP_PHONE,
                amount=db_order.total_amount,
                currency=ManualPaymentCurrency.RUB,
                seller_phone_e164="+79990000000",
                seller_phone_display="+7 999 000-00-00",
                payment_comment="ORD-99005612",
                status=ManualPaymentStatus.PENDING,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            session.add(payment)
            await session.commit()
            payment_id = payment.id
            order_id = db_order.id
            user_id = user.id

        async with sessions() as session:
            async def fail_commit() -> None:
                raise RuntimeError("forced commit failure")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError, match="forced commit failure"):
                await ManualPaymentsService(session).submit(
                    order_id=order_id,
                    user_id=user_id,
                    idempotency_key="payment-submit-99005612",
                )

        async with sessions() as session:
            stored = await session.get(ManualPayment, payment_id)
            assert stored is not None
            assert stored.status == ManualPaymentStatus.PENDING
            assert stored.submitted_at is None
            assert await session.scalar(
                select(func.count(CustomerInAppNotification.id)).where(
                    CustomerInAppNotification.manual_payment_id == payment_id
                )
            ) == 0
            assert await session.scalar(
                select(func.count(OutboxEvent.id)).where(
                    OutboxEvent.aggregate_type == "manual_payment",
                    OutboxEvent.aggregate_id == str(payment_id),
                )
            ) == 0
            assert await session.scalar(
                select(func.count(IdempotencyRecord.id)).where(
                    IdempotencyRecord.user_id == user_id,
                    IdempotencyRecord.scope == "manual_payments.submit",
                    IdempotencyRecord.key == "payment-submit-99005612",
                )
            ) == 0
    finally:
        async with sessions() as session:
            if payment_id is not None:
                await session.execute(
                    delete(OutboxEvent).where(
                        OutboxEvent.aggregate_type == "manual_payment",
                        OutboxEvent.aggregate_id == str(payment_id),
                    )
                )
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is required")
@pytest.mark.asyncio
async def test_postgres_concurrent_legacy_conversion_creates_at_most_one_row() -> None:
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    telegram_id = 99005607
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            user = User(telegram_id=telegram_id)
            session.add(user)
            await session.flush()
            db_order = _db_order(user.id, "ORD-99005607", status=OrderStatus.PROCESSING)
            session.add(db_order)
            await session.flush()
            payment = ManualPayment(
                order_id=db_order.id,
                method=ManualPaymentMethod.SBP_PHONE,
                amount=db_order.total_amount,
                currency=ManualPaymentCurrency.RUB,
                seller_phone_e164="+79990000000",
                seller_phone_display="+7 999 000-00-00",
                payment_comment="ORD-99005607",
                status=ManualPaymentStatus.APPROVED,
                approved_at=NOW,
                expires_at=NOW,
            )
            session.add(payment)
            await session.commit()
            user_id = user.id
            payment_id = payment.id

        async def load_pending():
            async with sessions() as session:
                return await CustomerInAppNotificationsService(session).pending(
                    user_id=user_id, limit=20
                )

        first, second = await asyncio.gather(load_pending(), load_pending())
        assert len(first) == 1
        assert len(second) == 1
        async with sessions() as session:
            count = await session.scalar(
                select(CustomerInAppNotification.id).where(
                    CustomerInAppNotification.source_key == f"payment:{payment_id}:APPROVED"
                )
            )
            assert count is not None
            rows = (
                await session.scalars(
                    select(CustomerInAppNotification).where(
                        CustomerInAppNotification.source_key == f"payment:{payment_id}:APPROVED"
                    )
                )
            ).all()
            assert len(rows) == 1
    finally:
        async with sessions() as session:
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
            await session.commit()
        await engine.dispose()


def _db_notification(user_id: int, source_key: str, occurred_at: datetime):
    return CustomerInAppNotification(
        user_id=user_id,
        category=CustomerInAppNotificationCategory.ORDER,
        event_code="PROCESSING",
        variant=CustomerInAppNotificationVariant.STANDARD,
        action_mode=CustomerInAppNotificationActionMode.CONTINUE_ONLY,
        title="Test",
        message=source_key,
        payload={},
        occurred_at=occurred_at,
        source_key=source_key,
    )


def _db_order(
    user_id: int,
    order_number: str,
    *,
    status: OrderStatus = OrderStatus.NEW,
) -> Order:
    return Order(
        order_number=order_number,
        user_id=user_id,
        status=status,
        subtotal_amount=Decimal("1000.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("1000.00"),
        delivery_price=Decimal("0.00"),
        contact_name="Test Customer",
        contact_phone="+79990000000",
        delivery_method=OrderDeliveryMethod.CDEK,
        delivery_address="Test address",
    )
