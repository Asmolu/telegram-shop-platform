import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import AppError
from app.db.base import Base
from app.db.models import (
    CustomerInAppNotification,
    CustomerInAppNotificationActionMode,
    CustomerInAppNotificationCategory,
    CustomerInAppNotificationVariant,
    ManualPaymentStatus,
    OrderDeliveryMethod,
    OrderStatus,
    ReturnRequestStatus,
    User,
)
from app.modules.customer_in_app_notifications.service import CustomerInAppNotificationsService

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
async def test_initial_order_payment_and_return_statuses_create_no_notifications() -> None:
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

    await service.create_order_status(new_order, occurred_at=NOW)
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

    await service.create_order_status(changed_order, occurred_at=NOW)
    await service.create_payment_status(payment, occurred_at=NOW)
    await service.create_return_status(return_request, occurred_at=NOW)

    order_notification, payment_notification, return_notification = session.added
    assert order_notification.source_key == "order:10:PROCESSING"
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
