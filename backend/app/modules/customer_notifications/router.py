from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.common.pagination import PaginationParams
from app.db.models import CustomerServiceNotificationDeliveryStatus, User, UserRole
from app.modules.customer_notifications.schemas import (
    CustomerServiceNotificationDeliveryList,
    CustomerSubscriptionList,
    CustomerSubscriptionMe,
    CustomerSubscriptionStartLink,
    CustomerSubscriptionUpdate,
)
from app.modules.customer_notifications.service import CustomerNotificationsService

router = APIRouter(prefix="/customer-notifications", tags=["customer-notifications"])


def get_customer_notifications_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerNotificationsService:
    return CustomerNotificationsService(session)


@router.get("/me/subscription", response_model=CustomerSubscriptionMe)
async def get_my_subscription(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        CustomerNotificationsService,
        Depends(get_customer_notifications_service),
    ],
) -> CustomerSubscriptionMe:
    return await service.get_my_subscription(current_user)


@router.patch("/me/subscription", response_model=CustomerSubscriptionMe)
async def update_my_subscription(
    payload: CustomerSubscriptionUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        CustomerNotificationsService,
        Depends(get_customer_notifications_service),
    ],
) -> CustomerSubscriptionMe:
    return await service.update_my_subscription(user=current_user, payload=payload)


@router.post("/me/start-link", response_model=CustomerSubscriptionStartLink)
async def create_my_start_link(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[
        CustomerNotificationsService,
        Depends(get_customer_notifications_service),
    ],
) -> CustomerSubscriptionStartLink:
    return await service.create_start_link(current_user)


@router.get("/subscriptions", response_model=CustomerSubscriptionList)
async def list_subscriptions(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationsService,
        Depends(get_customer_notifications_service),
    ],
    has_chat: Annotated[bool | None, Query()] = None,
    service_opt_in: Annotated[bool | None, Query()] = None,
    marketing_opt_in: Annotated[bool | None, Query()] = None,
    blocked: Annotated[bool | None, Query()] = None,
    user_id: Annotated[int | None, Query(ge=1)] = None,
    telegram_username: Annotated[str | None, Query(max_length=255)] = None,
) -> CustomerSubscriptionList:
    return await service.list_subscriptions(
        limit=pagination.limit,
        offset=pagination.offset,
        has_chat=has_chat,
        service_opt_in=service_opt_in,
        marketing_opt_in=marketing_opt_in,
        blocked=blocked,
        user_id=user_id,
        telegram_username=telegram_username,
    )


@router.get("/service-deliveries", response_model=CustomerServiceNotificationDeliveryList)
async def list_service_deliveries(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[
        CustomerNotificationsService,
        Depends(get_customer_notifications_service),
    ],
    status_filter: Annotated[
        CustomerServiceNotificationDeliveryStatus | None,
        Query(alias="status"),
    ] = None,
    event_name: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    user_id: Annotated[int | None, Query(ge=1)] = None,
    order_id: Annotated[int | None, Query(ge=1)] = None,
) -> CustomerServiceNotificationDeliveryList:
    return await service.list_service_deliveries(
        limit=pagination.limit,
        offset=pagination.offset,
        status=status_filter,
        event_name=event_name,
        user_id=user_id,
        order_id=order_id,
    )
