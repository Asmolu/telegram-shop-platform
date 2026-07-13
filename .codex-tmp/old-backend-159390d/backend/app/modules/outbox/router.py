from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.outbox.schemas import OutboxDiagnostics, OutboxEventDiagnostic
from app.modules.outbox.service import OutboxService

router = APIRouter(prefix="/outbox/admin", tags=["outbox"])


def get_outbox_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> OutboxService:
    return OutboxService(session)


@router.get("/diagnostics", response_model=OutboxDiagnostics)
async def diagnostics(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[OutboxService, Depends(get_outbox_service)],
    failed_limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> OutboxDiagnostics:
    return await service.diagnostics(failed_limit=failed_limit)


@router.post("/{event_id}/retry", response_model=OutboxEventDiagnostic)
async def retry_failed_event(
    event_id: UUID,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    service: Annotated[OutboxService, Depends(get_outbox_service)],
) -> OutboxEventDiagnostic:
    event = await service.retry_failed(event_id)
    return service._diagnostic(event)
