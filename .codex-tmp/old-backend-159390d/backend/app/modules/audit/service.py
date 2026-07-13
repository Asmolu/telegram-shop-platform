from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import AuditLog
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditLogList, AuditLogRead


class AuditService:
    """Seller/admin action audit logging."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AuditRepository(session)

    async def record_action(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = False,
    ) -> AuditLog:
        log = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=self.json_safe(before_data),
            after_data=self.json_safe(after_data),
            audit_metadata=self.json_safe(metadata),
        )
        self.repository.add(log)
        if commit:
            try:
                await self.session.commit()
                await self.session.refresh(log)
            except IntegrityError as exc:
                await self.session.rollback()
                raise AppError("Audit log create failed", status.HTTP_409_CONFLICT) from exc
        return log

    async def list_logs(
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
    ) -> AuditLogList:
        logs, total = await self.repository.list(
            limit=limit,
            offset=offset,
            action=action,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            created_from=created_from,
            created_to=created_to,
        )
        return AuditLogList(
            items=[AuditLogRead.model_validate(log) for log in logs],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_log(self, log_id: int) -> AuditLogRead:
        log = await self.repository.get_by_id(log_id)
        if log is None:
            raise AppError("Audit log not found", status.HTTP_404_NOT_FOUND)
        return AuditLogRead.model_validate(log)

    def snapshot(self, instance: object, fields: tuple[str, ...]) -> dict[str, Any]:
        return {field: self.json_safe(getattr(instance, field)) for field in fields}

    def json_safe(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self.json_safe(item) for key, item in value.items()}
        if isinstance(value, list | tuple | set):
            return [self.json_safe(item) for item in value]
        return value


class NoopAuditService:
    """No-op audit logger for direct service unit tests and non-API callers."""

    async def record_action(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = False,
    ) -> None:
        del (
            actor_user_id,
            action,
            entity_type,
            entity_id,
            before_data,
            after_data,
            metadata,
            commit,
        )

    def snapshot(self, instance: object, fields: tuple[str, ...]) -> dict[str, Any]:
        del instance, fields
        return {}
