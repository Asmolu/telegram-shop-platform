from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.errors import AppError
from app.db.models import AnalyticsEvent
from app.db.session import async_session_factory
from app.modules.analytics.repository import AnalyticsRepository
from app.modules.analytics.schemas import (
    AnalyticsEventList,
    AnalyticsEventRead,
    AnalyticsSummary,
    DashboardRevenueMonth,
    DashboardSummary,
    TopBannerSummary,
    TopProductSummary,
    TopPromoCodeSummary,
)
from app.modules.products.search import sanitize_search_query

logger = logging.getLogger(__name__)
SELLER_TIMEZONE = ZoneInfo("Europe/Moscow")


class AnalyticsTracker(Protocol):
    async def track(
        self,
        event_name: str,
        *,
        user_id: int | None = None,
        product_id: int | None = None,
        order_id: int | None = None,
        promo_code_id: int | None = None,
        banner_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record an analytics event without affecting the caller's transaction."""


class IsolatedAnalyticsTracker:
    """Writes analytics events in their own session so business flows stay isolated."""

    async def track(
        self,
        event_name: str,
        *,
        user_id: int | None = None,
        product_id: int | None = None,
        order_id: int | None = None,
        promo_code_id: int | None = None,
        banner_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            async with async_session_factory() as session:
                await AnalyticsService(session).record_event(
                    event_name=event_name,
                    user_id=user_id,
                    product_id=product_id,
                    order_id=order_id,
                    promo_code_id=promo_code_id,
                    banner_id=banner_id,
                    metadata=metadata,
                    commit=True,
                )
        except Exception:
            logger.warning("Failed to record analytics event %s", event_name, exc_info=True)


class AnalyticsService:
    """Analytics event capture and reporting."""

    def __init__(self, session: AsyncSession, *, now_factory=None) -> None:
        self.session = session
        self.repository = AnalyticsRepository(session)
        self.now_factory = now_factory or (lambda: datetime.now(SELLER_TIMEZONE))

    async def record_event(
        self,
        *,
        event_name: str,
        user_id: int | None = None,
        product_id: int | None = None,
        order_id: int | None = None,
        promo_code_id: int | None = None,
        banner_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = False,
    ) -> AnalyticsEvent:
        event = AnalyticsEvent(
            event_name=event_name,
            user_id=user_id,
            product_id=product_id,
            order_id=order_id,
            promo_code_id=promo_code_id,
            banner_id=banner_id,
            event_metadata=metadata,
        )
        self.repository.add(event)
        if commit:
            try:
                await self.session.commit()
                await self.session.refresh(event)
            except IntegrityError as exc:
                await self.session.rollback()
                raise AppError(
                    "Analytics event create failed",
                    status.HTTP_409_CONFLICT,
                ) from exc
        return event

    async def list_events(
        self,
        *,
        limit: int,
        offset: int,
        event_name: str | None = None,
        user_id: int | None = None,
        product_id: int | None = None,
        order_id: int | None = None,
        promo_code_id: int | None = None,
        banner_id: int | None = None,
        search: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> AnalyticsEventList:
        sanitized_search = sanitize_search_query(search)
        events, total = await self.repository.list(
            limit=limit,
            offset=offset,
            event_name=event_name,
            user_id=user_id,
            product_id=product_id,
            order_id=order_id,
            promo_code_id=promo_code_id,
            banner_id=banner_id,
            search=sanitized_search,
            created_from=created_from,
            created_to=created_to,
        )
        return AnalyticsEventList(
            items=[AnalyticsEventRead.model_validate(event) for event in events],
            meta=PageMeta(limit=limit, offset=offset, total=total),
        )

    async def get_summary(
        self,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> AnalyticsSummary:
        top_products = await self.repository.top_products_by_views(
            limit=10,
            created_from=created_from,
            created_to=created_to,
        )
        top_promo_codes = await self.repository.top_promo_codes_by_usage(
            limit=10,
            created_from=created_from,
            created_to=created_to,
        )
        top_banners = await self.repository.top_banners_by_clicks(
            limit=10,
            created_from=created_from,
            created_to=created_to,
        )
        return AnalyticsSummary(
            total_orders=await self.repository.count_orders(
                created_from=created_from,
                created_to=created_to,
            ),
            total_revenue=await self.repository.sum_order_revenue(
                created_from=created_from,
                created_to=created_to,
            ),
            product_views_count=await self.repository.count_events(
                "product.viewed",
                created_from=created_from,
                created_to=created_to,
            ),
            cart_item_added_count=await self.repository.count_events(
                "cart.item_added",
                created_from=created_from,
                created_to=created_to,
            ),
            checkout_started_count=await self.repository.count_events(
                "checkout.started",
                created_from=created_from,
                created_to=created_to,
            ),
            order_created_count=await self.repository.count_events(
                "order.created",
                created_from=created_from,
                created_to=created_to,
            ),
            promo_used_count=await self.repository.count_events(
                "promo.used",
                created_from=created_from,
                created_to=created_to,
            ),
            banner_clicked_count=await self.repository.count_events(
                "banner.clicked",
                created_from=created_from,
                created_to=created_to,
            ),
            top_products=[
                TopProductSummary(
                    product_id=product_id,
                    product_name=product_name,
                    view_count=view_count,
                )
                for product_id, product_name, view_count in top_products
            ],
            top_promo_codes=[
                TopPromoCodeSummary(
                    promo_code_id=promo_code_id,
                    promo_code=promo_code,
                    used_count=used_count,
                )
                for promo_code_id, promo_code, used_count in top_promo_codes
            ],
            top_banners=[
                TopBannerSummary(
                    banner_id=banner_id,
                    banner_title=banner_title,
                    click_count=click_count,
                )
                for banner_id, banner_title, click_count in top_banners
            ],
        )

    async def get_dashboard_summary(self) -> DashboardSummary:
        now = self._now().astimezone(SELLER_TIMEZONE)
        period_start, period_end = self._current_month_interval(now)
        orders_count, gross_revenue, discount_total, net_revenue = (
            await self.repository.revenue_for_orders(
                period_start=period_start,
                period_end=period_end,
            )
        )
        return DashboardSummary(
            active_orders_count=await self.repository.count_active_orders(),
            active_banners_count=await self.repository.count_active_banners(now=now),
            products_total=await self.repository.count_products_total(),
            products_out_of_stock=await self.repository.count_products_out_of_stock(),
            revenue_month=DashboardRevenueMonth(
                period_start=period_start,
                period_end=period_end,
                orders_count=orders_count,
                gross_revenue=gross_revenue,
                discount_total=discount_total,
                net_revenue=net_revenue,
            ),
        )

    def _now(self) -> datetime:
        return self.now_factory()

    @staticmethod
    def _current_month_interval(now: datetime) -> tuple[datetime, datetime]:
        period_start = datetime(now.year, now.month, 1, tzinfo=SELLER_TIMEZONE)
        if now.month == 12:
            period_end = datetime(now.year + 1, 1, 1, tzinfo=SELLER_TIMEZONE)
        else:
            period_end = datetime(now.year, now.month + 1, 1, tzinfo=SELLER_TIMEZONE)
        return period_start, period_end
