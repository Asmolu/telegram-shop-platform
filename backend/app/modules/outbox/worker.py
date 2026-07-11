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
)
from app.db.session import async_session_factory
from app.modules.customer_notifications.service import (
    CustomerServiceNotificationDeliveryService,
)
from app.modules.manual_payments.service import ManualPaymentEventPublisher
from app.modules.notifications.service import NotificationsService
from app.modules.outbox.constants import CUSTOMER_CONSUMER, SELLER_CONSUMER
from app.modules.outbox.repository import OutboxRepository
from app.modules.outbox.schemas import OutboxClaim
from app.modules.outbox.service import OutboxService

logger = logging.getLogger(__name__)


def default_worker_id() -> str:
    configured = settings.outbox_worker_id
    if configured and configured.strip():
        return configured.strip()[:255]
    return f"{socket.gethostname()}:{os.getpid()}"[:255]


def heartbeat_interval_seconds(lock_timeout_seconds: int) -> float:
    """Renew at one third of the lease timeout, safely below stale recovery."""
    return lock_timeout_seconds / 3


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
        claims = await repository.claim_due(
            now=now,
            stale_before=now - timedelta(seconds=settings.outbox_lock_timeout_seconds),
            worker_id=worker_id or default_worker_id(),
            limit=settings.outbox_batch_size,
        )
        await session.commit()

    current_worker_id = worker_id or default_worker_id()
    for claim in claims:
        if claim.recovered_stale:
            logger.warning(
                "outbox stale claim recovered",
                extra={
                    "event_database_id": claim.database_id,
                    "event_id": str(claim.event_id),
                    "event_name": claim.event_name,
                    "worker_id": current_worker_id,
                    "attempt": claim.attempt_count,
                },
            )
        await _process_claimed_event(claim, worker_id=current_worker_id)
    return len(claims)


async def _process_claimed_event(
    claim: OutboxClaim,
    *,
    worker_id: str,
) -> None:
    heartbeat_stop = asyncio.Event()
    ownership_lost = asyncio.Event()
    heartbeat = asyncio.create_task(
        _heartbeat_claim(
            claim,
            worker_id=worker_id,
            stop_event=heartbeat_stop,
            ownership_lost=ownership_lost,
        )
    )
    try:
        for consumer in claim.pending_consumers:
            if ownership_lost.is_set():
                break
            try:
                await dispatch_outbox_delivery(
                    event_id=claim.event_id,
                    event_name=claim.event_name,
                    payload=dict(claim.payload),
                    consumer=consumer,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "outbox delivery failed",
                    extra={
                        "event_id": str(claim.event_id),
                        "event_name": claim.event_name,
                        "consumer": consumer,
                        "worker_id": worker_id,
                        "attempt": claim.attempt_count,
                        "error_type": type(exc).__name__,
                    },
                )
                if ownership_lost.is_set():
                    break
                async with async_session_factory() as session:
                    acknowledged = await OutboxService(session).mark_delivery_failed(
                        event_database_id=claim.database_id,
                        event_id=claim.event_id,
                        claim_token=claim.claim_token,
                        consumer=consumer,
                        error=exc,
                    )
            else:
                if ownership_lost.is_set():
                    break
                async with async_session_factory() as session:
                    acknowledged = await OutboxService(session).mark_delivery_processed(
                        event_database_id=claim.database_id,
                        event_id=claim.event_id,
                        claim_token=claim.claim_token,
                        consumer=consumer,
                    )
            if not acknowledged:
                ownership_lost.set()
                break
    except asyncio.CancelledError:
        heartbeat.cancel()
        raise
    finally:
        heartbeat_stop.set()
        await asyncio.gather(heartbeat, return_exceptions=True)

    if ownership_lost.is_set():
        logger.warning(
            "outbox claim ownership lost; final acknowledgement skipped",
            extra={
                "event_id": str(claim.event_id),
                "event_name": claim.event_name,
                "worker_id": worker_id,
                "attempt": claim.attempt_count,
            },
        )
        return
    async with async_session_factory() as session:
        await OutboxService(session).finish_attempt(
            event_database_id=claim.database_id,
            event_id=claim.event_id,
            claim_token=claim.claim_token,
        )


async def _heartbeat_claim(
    claim: OutboxClaim,
    *,
    worker_id: str,
    stop_event: asyncio.Event,
    ownership_lost: asyncio.Event,
) -> None:
    interval = heartbeat_interval_seconds(settings.outbox_lock_timeout_seconds)
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        try:
            async with async_session_factory() as session:
                renewed = await OutboxService(session).renew_claim(
                    event_database_id=claim.database_id,
                    event_id=claim.event_id,
                    claim_token=claim.claim_token,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "outbox lease renewal failed",
                extra={
                    "event_id": str(claim.event_id),
                    "event_name": claim.event_name,
                    "worker_id": worker_id,
                    "attempt": claim.attempt_count,
                    "error_type": type(exc).__name__,
                },
            )
            ownership_lost.set()
            return
        if not renewed:
            ownership_lost.set()
            return


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
