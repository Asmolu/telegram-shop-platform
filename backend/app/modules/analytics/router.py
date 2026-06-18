from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import get_db_session, require_roles
from app.db.models import User, UserRole
from app.modules.analytics.schemas import AnalyticsEventList, AnalyticsSummary, DashboardSummary
from app.modules.analytics.service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])
dashboard_router = APIRouter(prefix="/admin/dashboard", tags=["dashboard"])


def get_analytics_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AnalyticsService:
    return AnalyticsService(session)


@router.get("/events", response_model=AnalyticsEventList)
async def list_analytics_events(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    event_name: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    user_id: int | None = None,
    product_id: int | None = None,
    order_id: int | None = None,
    promo_code_id: int | None = None,
    banner_id: int | None = None,
    search: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AnalyticsEventList:
    return await service.list_events(
        limit=limit,
        offset=offset,
        event_name=event_name,
        user_id=user_id,
        product_id=product_id,
        order_id=order_id,
        promo_code_id=promo_code_id,
        banner_id=banner_id,
        search=search,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AnalyticsSummary:
    return await service.get_summary(created_from=created_from, created_to=created_to)


@dashboard_router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    _: Annotated[User, Depends(require_roles(UserRole.SELLER, UserRole.ADMIN))],
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> DashboardSummary:
    return await service.get_dashboard_summary()
