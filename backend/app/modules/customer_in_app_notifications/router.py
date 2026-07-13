from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session
from app.db.models import User
from app.modules.customer_in_app_notifications.schemas import (
    CustomerInAppNotificationRead,
    CustomerInAppNotificationSeenRead,
)
from app.modules.customer_in_app_notifications.service import CustomerInAppNotificationsService

router = APIRouter(prefix="/customer-in-app-notifications", tags=["customer-in-app-notifications"])


def get_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerInAppNotificationsService:
    return CustomerInAppNotificationsService(session)


@router.get("/pending", response_model=list[CustomerInAppNotificationRead])
async def pending(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerInAppNotificationsService, Depends(get_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[CustomerInAppNotificationRead]:
    return await service.pending(user_id=current_user.id, limit=limit)


@router.post("/{notification_id}/seen", response_model=CustomerInAppNotificationSeenRead)
async def mark_seen(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[CustomerInAppNotificationsService, Depends(get_service)],
) -> CustomerInAppNotificationSeenRead:
    return await service.mark_seen(notification_id=notification_id, user_id=current_user.id)
