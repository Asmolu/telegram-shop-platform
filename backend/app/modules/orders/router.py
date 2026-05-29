from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_current_user, get_db_session, require_roles
from app.db.models import OrderStatus, User, UserRole
from app.modules.analytics.service import IsolatedAnalyticsTracker
from app.modules.audit.service import AuditService
from app.modules.orders.schemas import (
    OrderCheckoutCreate,
    OrderList,
    OrderRead,
    OrderStatusUpdate,
)
from app.modules.orders.service import OrdersService

router = APIRouter(prefix="/orders", tags=["orders"])


def get_orders_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> OrdersService:
    return OrdersService(
        session,
        analytics_tracker=IsolatedAnalyticsTracker(),
        audit_service=AuditService(session),
    )


@router.post("/checkout", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def checkout_current_user_cart(
    payload: OrderCheckoutCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> OrderRead:
    return await service.checkout_current_user_cart(current_user.id, payload)


@router.get("", response_model=OrderList)
async def list_current_user_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderList:
    return await service.list_current_user_orders(current_user.id, limit=limit, offset=offset)


@router.get("/admin", response_model=OrderList)
async def list_orders(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[OrdersService, Depends(get_orders_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    user_id: int | None = None,
    search: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
) -> OrderList:
    return await service.list_orders(
        limit=limit,
        offset=offset,
        status=status_filter,
        user_id=user_id,
        search=search,
    )


@router.get("/admin/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: int,
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> OrderRead:
    return await service.get_order(order_id)


@router.patch("/admin/{order_id}/status", response_model=OrderRead)
async def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> OrderRead:
    return await service.update_order_status(order_id, payload, actor_user_id=current_user.id)


@router.get("/{order_id}", response_model=OrderRead)
async def get_current_user_order(
    order_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[OrdersService, Depends(get_orders_service)],
) -> OrderRead:
    return await service.get_current_user_order(current_user.id, order_id)
