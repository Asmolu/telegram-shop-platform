import json
import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    OutboxDelivery,
    OutboxDeliveryStatus,
    OutboxEvent,
    OutboxStatus,
)
from app.modules.outbox.repository import OutboxRepository
from app.modules.outbox.schemas import OutboxDiagnostics, OutboxEventDiagnostic

OUTBOX_ERROR_MAX_LENGTH = 2000
logger = logging.getLogger(__name__)


def retry_delay_seconds(attempt_count: int, *, base_seconds: int, max_seconds: int) -> int:
    exponent = max(0, attempt_count - 1)
    return min(max_seconds, base_seconds * (2**exponent))


def sanitize_outbox_error(error: BaseException) -> str:
    message = " ".join((str(error) or type(error).__name__).split())
    for secret in (
        settings.telegram_bot_token,
        settings.telegram_webapp_bot_token,
        settings.telegram_customer_bot_token,
        settings.telegram_seller_webhook_secret,
        settings.telegram_customer_webhook_secret,
        settings.jwt_secret_key,
    ):
        if secret and secret != "change-me-in-local-env":
            message = message.replace(secret, "[redacted]")
    return message[:OUTBOX_ERROR_MAX_LENGTH]


class OutboxService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = OutboxRepository(session)

    def enqueue(
        self,
        *,
        event_name: str,
        aggregate_type: str,
        aggregate_id: int | str,
        payload: Mapping[str, object],
        consumers: Iterable[str],
        event_id: UUID | None = None,
        max_attempts: int | None = None,
    ) -> OutboxEvent:
        encoded = jsonable_encoder(dict(payload))
        if not isinstance(encoded, dict):
            raise ValueError("Outbox payload must encode to a JSON object")
        json.dumps(encoded, ensure_ascii=False, allow_nan=False)
        consumer_names = tuple(dict.fromkeys(value.strip() for value in consumers if value.strip()))
        if not consumer_names:
            raise ValueError("Outbox event requires at least one consumer")
        event = OutboxEvent(
            event_id=event_id or uuid4(),
            event_name=event_name,
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id),
            payload=encoded,
            status=OutboxStatus.PENDING,
            attempt_count=0,
            max_attempts=max_attempts or settings.outbox_max_attempts,
            next_attempt_at=datetime.now(UTC),
            deliveries=[
                OutboxDelivery(consumer=consumer, status=OutboxDeliveryStatus.PENDING)
                for consumer in consumer_names
            ],
        )
        self.repository.add(event)
        return event

    async def mark_delivery_processed(
        self,
        *,
        event_database_id: int,
        event_id: UUID,
        claim_token: UUID,
        consumer: str,
    ) -> bool:
        event = await self.repository.get_owned_with_deliveries(
            event_database_id=event_database_id,
            claim_token=claim_token,
            for_update=True,
        )
        if event is None:
            self._log_stale_ack(event_id, consumer, "success")
            return False
        delivery = self._delivery(event, consumer)
        if delivery.status == OutboxDeliveryStatus.PROCESSED:
            return True
        if delivery.last_claim_token == claim_token:
            return True
        delivery.status = OutboxDeliveryStatus.PROCESSED
        delivery.processed_at = datetime.now(UTC)
        delivery.last_error = None
        delivery.last_claim_token = claim_token
        await self.session.commit()
        return True

    async def mark_delivery_failed(
        self,
        *,
        event_database_id: int,
        event_id: UUID,
        claim_token: UUID,
        consumer: str,
        error: BaseException,
    ) -> bool:
        event = await self.repository.get_owned_with_deliveries(
            event_database_id=event_database_id,
            claim_token=claim_token,
            for_update=True,
        )
        if event is None:
            self._log_stale_ack(event_id, consumer, "failure")
            return False
        delivery = self._delivery(event, consumer)
        if delivery.status == OutboxDeliveryStatus.PROCESSED:
            return True
        if delivery.last_claim_token == claim_token:
            return True
        delivery.attempt_count += 1
        delivery.last_claim_token = claim_token
        delivery.last_error = sanitize_outbox_error(error)
        event.last_error = delivery.last_error
        if delivery.attempt_count >= event.max_attempts:
            delivery.status = OutboxDeliveryStatus.FAILED
        await self.session.commit()
        return True

    async def finish_attempt(
        self, *, event_database_id: int, event_id: UUID, claim_token: UUID
    ) -> bool:
        event = await self.repository.get_owned_with_deliveries(
            event_database_id=event_database_id,
            claim_token=claim_token,
            for_update=True,
        )
        if event is None:
            self._log_stale_ack(event_id, None, "finish")
            return False
        await self._finalize_event(event)
        await self.session.commit()
        return True

    async def renew_claim(
        self, *, event_database_id: int, event_id: UUID, claim_token: UUID
    ) -> bool:
        renewed = await self.repository.renew_claim(
            event_database_id=event_database_id,
            claim_token=claim_token,
            now=datetime.now(UTC),
        )
        if renewed:
            await self.session.commit()
            return True
        await self.session.rollback()
        logger.warning(
            "outbox claim lease renewal lost ownership",
            extra={"event_id": str(event_id), "acknowledgement_result": "stale"},
        )
        return False

    async def retry_failed(self, event_id: UUID) -> OutboxEvent:
        event = await self.repository.get_with_deliveries(event_id, for_update=True)
        if event is None:
            raise AppError("Outbox event not found", 404)
        if event.status != OutboxStatus.FAILED:
            raise AppError("Only failed outbox events can be retried", 400)
        for delivery in event.deliveries:
            if delivery.status == OutboxDeliveryStatus.FAILED:
                delivery.status = OutboxDeliveryStatus.PENDING
                delivery.attempt_count = 0
                delivery.last_error = None
                delivery.processed_at = None
        event.status = OutboxStatus.PENDING
        event.attempt_count = 0
        event.next_attempt_at = datetime.now(UTC)
        event.locked_at = None
        event.locked_by = None
        event.claim_token = None
        event.processed_at = None
        event.last_error = None
        await self.session.commit()
        return event

    async def diagnostics(self, *, failed_limit: int = 50) -> OutboxDiagnostics:
        counts = await self.repository.counts()
        oldest = await self.repository.oldest_pending()
        failed = await self.repository.list_failed(limit=failed_limit)
        return OutboxDiagnostics(
            pending_count=counts.get(OutboxStatus.PENDING.value, 0),
            processing_count=counts.get(OutboxStatus.PROCESSING.value, 0),
            processed_count=counts.get(OutboxStatus.PROCESSED.value, 0),
            failed_count=counts.get(OutboxStatus.FAILED.value, 0),
            oldest_pending=self._diagnostic(oldest) if oldest else None,
            failed_events=[self._diagnostic(event) for event in failed],
        )

    async def _finalize_event(self, event: OutboxEvent) -> None:
        pending = [d for d in event.deliveries if d.status == OutboxDeliveryStatus.PENDING]
        failed = [d for d in event.deliveries if d.status == OutboxDeliveryStatus.FAILED]
        now = datetime.now(UTC)
        event.locked_at = None
        event.locked_by = None
        event.claim_token = None
        if pending:
            event.status = OutboxStatus.PENDING
            event.next_attempt_at = now + timedelta(
                seconds=retry_delay_seconds(
                    max((d.attempt_count for d in pending), default=event.attempt_count),
                    base_seconds=settings.outbox_retry_base_seconds,
                    max_seconds=settings.outbox_retry_max_seconds,
                )
            )
            return
        if failed:
            event.status = OutboxStatus.FAILED
            event.processed_at = None
            return
        event.status = OutboxStatus.PROCESSED
        event.processed_at = now
        event.last_error = None

    @staticmethod
    def _delivery(event: OutboxEvent, consumer: str) -> OutboxDelivery:
        for delivery in event.deliveries:
            if delivery.consumer == consumer:
                return delivery
        raise RuntimeError("Outbox delivery disappeared")

    @staticmethod
    def _log_stale_ack(event_id: UUID, consumer: str | None, acknowledgement: str) -> None:
        logger.info(
            "stale outbox acknowledgement ignored",
            extra={
                "event_id": str(event_id),
                "consumer": consumer,
                "acknowledgement": acknowledgement,
                "acknowledgement_result": "stale",
            },
        )

    @staticmethod
    def _diagnostic(event: OutboxEvent) -> OutboxEventDiagnostic:
        return OutboxEventDiagnostic(
            event_id=event.event_id,
            event_name=event.event_name,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            status=event.status.value,
            attempt_count=event.attempt_count,
            max_attempts=event.max_attempts,
            next_attempt_at=event.next_attempt_at,
            locked_at=event.locked_at,
            locked_by=event.locked_by,
            processed_at=event.processed_at,
            last_error=event.last_error,
            created_at=event.created_at,
        )
