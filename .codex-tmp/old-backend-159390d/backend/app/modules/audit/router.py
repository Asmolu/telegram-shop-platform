from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.audit.schemas import AuditLogList, AuditLogRead
from app.modules.audit.service import AuditService

router = APIRouter(prefix="/audit-logs", tags=["audit"])


def get_audit_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> AuditService:
    return AuditService(session)


@router.get("", response_model=AuditLogList)
async def list_audit_logs(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[AuditService, Depends(get_audit_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    actor_user_id: int | None = None,
    entity_type: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    entity_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AuditLogList:
    return await service.list_logs(
        limit=limit,
        offset=offset,
        action=action,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/{log_id}", response_model=AuditLogRead)
async def get_audit_log(
    log_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[AuditService, Depends(get_audit_service)],
) -> AuditLogRead:
    return await service.get_log(log_id)
