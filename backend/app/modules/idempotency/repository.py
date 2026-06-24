from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IdempotencyRecord


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def cleanup_expired(self, *, now: datetime, user_id: int, scope: str) -> None:
        await self.session.execute(
            delete(IdempotencyRecord).where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.expires_at <= now,
            )
        )

    async def insert_processing(
        self,
        *,
        user_id: int,
        scope: str,
        key: str,
        request_hash: str,
        expires_at: datetime,
    ) -> int | None:
        statement = (
            insert(IdempotencyRecord)
            .values(
                user_id=user_id,
                scope=scope,
                key=key,
                request_hash=request_hash,
                status="PROCESSING",
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(
                constraint="uq_idempotency_records_user_scope_key",
            )
            .returning(IdempotencyRecord.id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, record_id: int) -> IdempotencyRecord | None:
        result = await self.session.execute(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.id == record_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_key_for_update(
        self,
        *,
        user_id: int,
        scope: str,
        key: str,
    ) -> IdempotencyRecord | None:
        result = await self.session.execute(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.user_id == user_id,
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key == key,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    def mark_succeeded(
        self,
        record: IdempotencyRecord,
        *,
        response_body: dict[str, Any],
        response_status_code: int,
        completed_at: datetime,
    ) -> None:
        record.status = "SUCCEEDED"
        record.response_body = response_body
        record.response_status_code = response_status_code
        record.completed_at = completed_at
