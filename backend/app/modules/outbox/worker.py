import asyncio
import logging
import os
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import settings
from app.db.models import (
    CustomerServiceNotificationDeliveryStatus,
    NotificationStatus,
    OutboxDeliveryStatus,
)
from app.db.session import async_session_factory
from app.modules.customer_notifications.service import (
    CustomerServiceNotificationDeliveryService,
)
from app.modules.manual_payments.service import ManualPaymentEventPublisher
from app.modules.notifications.service import NotificationsService
from app.modules.outbox.constants import CUSTOMER_CONSUMER, SELLER_CONSUMER
from app.modules.outbox.repository import OutboxRepository
from app.modules.outbox.service import OutboxService

logger = logging.getLogger(__name__)


def default_worker_id() -> str:
    configured = settings.outbox_worker_id
    if configured and configured.strip():
        return configured.strip()[:255]
    return f"{socket.gethostname()}:{os.getpid()}"[:255]


async def run_outbox_worker(stop_event: asyncio.Event) -> None:
    poll_seconds = max(0.1, settings.outbox_poll_interval_seconds)
    worker_id = default_worker_id()
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            continue
        except TimeoutError:
            pass
        try:
            await process_outbox_batch(worker_id=worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("outbox worker cycle failed", extra={"error_type": type(exc).__name__})


async def process_outbox_batch(*, worker_id: str | None = None) -> int:
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        repository = OutboxRepository(session)
        events = await repository.claim_due(
            now=now,
            stale_before=now - timedelta(seconds=max(1, settings.outbox_lock_timeout_seconds)),
            worker_id=worker_id or default_worker_id(),
            limit=max(1, settings.outbox_batch_size),
        )
        snapshots = [
            (
                event.event_id,
                event.event_name,
                dict(event.payload),
                [
                    delivery.consumer
                    for delivery in event.deliveries
                    if delivery.status == OutboxDeliveryStatus.PENDING
                ],
            )
            for event in events
        ]
        await session.commit()

    for event_id, event_name, payload, consumers in snapshots:
        await _process_claimed_event(event_id, event_name, payload, consumers)
    return len(snapshots)


async def _process_claimed_event(
    event_id: UUID,
    event_name: str,
    payload: dict[str, object],
    consumers: list[str],
) -> None:
    for consumer in consumers:
        try:
            await dispatch_outbox_delivery(
                event_id=event_id,
                event_name=event_name,
                payload=payload,
                consumer=consumer,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "outbox delivery failed",
                extra={
                    "event_id": str(event_id),
                    "event_name": event_name,
                    "consumer": consumer,
                    "error_type": type(exc).__name__,
                },
            )
            async with async_session_factory() as session:
                await OutboxService(session).mark_delivery_failed(
                    event_id=event_id, consumer=consumer, error=exc
                )
        else:
            async with async_session_factory() as session:
                await OutboxService(session).mark_delivery_processed(
                    event_id=event_id, consumer=consumer
                )
    async with async_session_factory() as session:
        await OutboxService(session).finish_attempt(event_id)


async def dispatch_outbox_delivery(
    *, event_id: UUID, event_name: str, payload: dict[str, object], consumer: str
) -> None:
    async with async_session_factory() as session:
        if consumer == SELLER_CONSUMER:
            if event_name.startswith("manual_payment."):
                await ManualPaymentEventPublisher(session).emit_seller(event_name, payload)
            else:
                notification = await NotificationsService(session).create_for_event(
                    name=event_name,
                    payload=payload,
                    source_event_id=event_id,
                    source_consumer=consumer,
                )
                if notification is not None and notification.status == NotificationStatus.FAILED:
                    raise RuntimeError(notification.error_message or "Seller delivery failed")
            return
        if consumer == CUSTOMER_CONSUMER:
            delivery = await CustomerServiceNotificationDeliveryService(
                session
            ).handle_order_event(
                name=event_name,
                payload=payload,
                source_event_id=event_id,
                source_consumer=consumer,
            )
            if delivery is not None and delivery.status == (
                CustomerServiceNotificationDeliveryStatus.FAILED
            ):
                raise RuntimeError(delivery.error_message or "Customer delivery failed")
            return
        raise ValueError(f"Unknown outbox consumer: {consumer}")
