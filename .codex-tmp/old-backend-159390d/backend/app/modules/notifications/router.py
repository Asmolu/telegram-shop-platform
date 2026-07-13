from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.common.pagination import PaginationParams
from app.db.models import NotificationChannel, NotificationStatus, User, UserRole
from app.modules.notifications.schemas import NotificationList, NotificationRead
from app.modules.notifications.service import NotificationsService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notifications_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NotificationsService:
    return NotificationsService(session)


@router.get("/status")
async def module_status() -> dict[str, str]:
    return {"module": "notifications", "status": "stub"}


@router.get("/me", response_model=NotificationList)
async def list_current_user_notifications(
    pagination: Annotated[PaginationParams, Depends()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[NotificationsService, Depends(get_notifications_service)],
) -> NotificationList:
    return await service.list_user_notifications(
        user_id=current_user.id,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/admin", response_model=NotificationList)
async def list_notifications(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[NotificationsService, Depends(get_notifications_service)],
    channel: NotificationChannel | None = None,
    status_filter: Annotated[NotificationStatus | None, Query(alias="status")] = None,
) -> NotificationList:
    return await service.list_notifications(
        limit=pagination.limit,
        offset=pagination.offset,
        channel=channel,
        status=status_filter,
    )


@router.get("/admin/{notification_id}", response_model=NotificationRead)
async def get_notification(
    notification_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[NotificationsService, Depends(get_notifications_service)],
) -> NotificationRead:
    return await service.get_notification(notification_id)


@router.post("/admin/{notification_id}/retry", response_model=NotificationRead)
async def retry_notification(
    notification_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[NotificationsService, Depends(get_notifications_service)],
) -> NotificationRead:
    return await service.retry_notification(notification_id)
