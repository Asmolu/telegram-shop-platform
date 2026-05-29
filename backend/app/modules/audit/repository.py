from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


class AuditRepository:
    """Database access layer for seller/admin audit logs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, log: AuditLog) -> None:
        self.session.add(log)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        action: str | None = None,
        actor_user_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        conditions = self._filters(
            action=action,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            created_from=created_from,
            created_to=created_to,
        )
        logs_result = await self.session.execute(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count(AuditLog.id)).where(*conditions)
        )
        return list(logs_result.scalars().all()), count_result.scalar_one()

    async def get_by_id(self, log_id: int) -> AuditLog | None:
        return await self.session.get(AuditLog, log_id)

    def _filters(
        self,
        *,
        action: str | None,
        actor_user_id: int | None,
        entity_type: str | None,
        entity_id: int | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[Any]:
        conditions: list[Any] = []
        if action is not None:
            conditions.append(AuditLog.action == action)
        if actor_user_id is not None:
            conditions.append(AuditLog.actor_user_id == actor_user_id)
        if entity_type is not None:
            conditions.append(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            conditions.append(AuditLog.entity_id == entity_id)
        if created_from is not None:
            conditions.append(AuditLog.created_at >= created_from)
        if created_to is not None:
            conditions.append(AuditLog.created_at <= created_to)
        return conditions
