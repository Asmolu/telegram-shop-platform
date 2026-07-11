from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class OutboxClaim:
    database_id: int
    event_id: UUID
    claim_token: UUID
    event_name: str
    payload: Mapping[str, object]
    pending_consumers: tuple[str, ...]
    attempt_count: int
    recovered_stale: bool

    @classmethod
    def create(
        cls,
        *,
        database_id: int,
        event_id: UUID,
        claim_token: UUID,
        event_name: str,
        payload: dict[str, object],
        pending_consumers: tuple[str, ...],
        attempt_count: int = 1,
        recovered_stale: bool = False,
    ) -> "OutboxClaim":
        return cls(
            database_id=database_id,
            event_id=event_id,
            claim_token=claim_token,
            event_name=event_name,
            payload=MappingProxyType(payload.copy()),
            pending_consumers=pending_consumers,
            attempt_count=attempt_count,
            recovered_stale=recovered_stale,
        )


class OutboxEventDiagnostic(BaseModel):
    event_id: UUID
    event_name: str
    aggregate_type: str
    aggregate_id: str
    status: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    locked_at: datetime | None
    locked_by: str | None
    processed_at: datetime | None
    last_error: str | None
    created_at: datetime


class OutboxDiagnostics(BaseModel):
    pending_count: int
    processing_count: int
    processed_count: int
    failed_count: int
    oldest_pending: OutboxEventDiagnostic | None
    failed_events: list[OutboxEventDiagnostic]
