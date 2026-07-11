from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
