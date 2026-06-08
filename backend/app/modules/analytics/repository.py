from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent, Banner, Order, Product, PromoCode


class AnalyticsRepository:
    """Database access layer for user behavior analytics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, event: AnalyticsEvent) -> None:
        self.session.add(event)

    async def list(
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
    ) -> tuple[list[AnalyticsEvent], int]:
        conditions = self._event_filters(
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
        events_result = await self.session.execute(
            select(AnalyticsEvent)
            .where(*conditions)
            .order_by(AnalyticsEvent.created_at.desc(), AnalyticsEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_result = await self.session.execute(
            select(func.count(AnalyticsEvent.id)).where(*conditions)
        )
        return list(events_result.scalars().all()), count_result.scalar_one()

    async def count_events(
        self,
        event_name: str,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        result = await self.session.execute(
            select(func.count(AnalyticsEvent.id)).where(
                *self._event_filters(
                    event_name=event_name,
                    user_id=None,
                    product_id=None,
                    order_id=None,
                    promo_code_id=None,
                    banner_id=None,
                    search=None,
                    created_from=created_from,
                    created_to=created_to,
                )
            )
        )
        return result.scalar_one()

    async def count_orders(
        self,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        result = await self.session.execute(
            select(func.count(Order.id)).where(
                *self._order_filters(created_from=created_from, created_to=created_to)
            )
        )
        return result.scalar_one()

    async def sum_order_revenue(
        self,
        *,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(Order.total_amount), Decimal("0.00"))).where(
                *self._order_filters(created_from=created_from, created_to=created_to)
            )
        )
        return result.scalar_one()

    async def top_products_by_views(
        self,
        *,
        limit: int,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[tuple[int, str | None, int]]:
        view_count = func.count(AnalyticsEvent.id).label("view_count")
        result = await self.session.execute(
            select(AnalyticsEvent.product_id, Product.name, view_count)
            .join(Product, Product.id == AnalyticsEvent.product_id, isouter=True)
            .where(
                AnalyticsEvent.event_name == "product.viewed",
                AnalyticsEvent.product_id.is_not(None),
                *self._created_at_filters(
                    AnalyticsEvent.created_at,
                    created_from=created_from,
                    created_to=created_to,
                ),
            )
            .group_by(AnalyticsEvent.product_id, Product.name)
            .order_by(view_count.desc(), AnalyticsEvent.product_id.asc())
            .limit(limit)
        )
        return [
            (int(row.product_id), row.name, int(row.view_count))
            for row in result.all()
            if row.product_id is not None
        ]

    async def top_promo_codes_by_usage(
        self,
        *,
        limit: int,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[tuple[int, str | None, int]]:
        used_count = func.count(AnalyticsEvent.id).label("used_count")
        result = await self.session.execute(
            select(AnalyticsEvent.promo_code_id, PromoCode.code, used_count)
            .join(PromoCode, PromoCode.id == AnalyticsEvent.promo_code_id, isouter=True)
            .where(
                AnalyticsEvent.event_name == "promo.used",
                AnalyticsEvent.promo_code_id.is_not(None),
                *self._created_at_filters(
                    AnalyticsEvent.created_at,
                    created_from=created_from,
                    created_to=created_to,
                ),
            )
            .group_by(AnalyticsEvent.promo_code_id, PromoCode.code)
            .order_by(used_count.desc(), AnalyticsEvent.promo_code_id.asc())
            .limit(limit)
        )
        return [
            (int(row.promo_code_id), row.code, int(row.used_count))
            for row in result.all()
            if row.promo_code_id is not None
        ]

    async def top_banners_by_clicks(
        self,
        *,
        limit: int,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[tuple[int, str | None, int]]:
        click_count = func.count(AnalyticsEvent.id).label("click_count")
        result = await self.session.execute(
            select(AnalyticsEvent.banner_id, Banner.title, click_count)
            .join(Banner, Banner.id == AnalyticsEvent.banner_id, isouter=True)
            .where(
                AnalyticsEvent.event_name == "banner.clicked",
                AnalyticsEvent.banner_id.is_not(None),
                *self._created_at_filters(
                    AnalyticsEvent.created_at,
                    created_from=created_from,
                    created_to=created_to,
                ),
            )
            .group_by(AnalyticsEvent.banner_id, Banner.title)
            .order_by(click_count.desc(), AnalyticsEvent.banner_id.asc())
            .limit(limit)
        )
        return [
            (int(row.banner_id), row.title, int(row.click_count))
            for row in result.all()
            if row.banner_id is not None
        ]

    def _event_filters(
        self,
        *,
        event_name: str | None,
        user_id: int | None,
        product_id: int | None,
        order_id: int | None,
        promo_code_id: int | None,
        banner_id: int | None,
        search: str | None,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[Any]:
        conditions: list[Any] = []
        if event_name is not None:
            conditions.append(AnalyticsEvent.event_name == event_name)
        if user_id is not None:
            conditions.append(AnalyticsEvent.user_id == user_id)
        if product_id is not None:
            conditions.append(AnalyticsEvent.product_id == product_id)
        if order_id is not None:
            conditions.append(AnalyticsEvent.order_id == order_id)
        if promo_code_id is not None:
            conditions.append(AnalyticsEvent.promo_code_id == promo_code_id)
        if banner_id is not None:
            conditions.append(AnalyticsEvent.banner_id == banner_id)
        if search is not None:
            search_pattern = f"%{search.strip()}%"
            conditions.append(
                or_(
                    AnalyticsEvent.event_name.ilike(search_pattern),
                    cast(AnalyticsEvent.event_metadata, String).ilike(search_pattern),
                )
            )
        conditions.extend(
            self._created_at_filters(
                AnalyticsEvent.created_at,
                created_from=created_from,
                created_to=created_to,
            )
        )
        return conditions

    def _order_filters(
        self,
        *,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[Any]:
        return self._created_at_filters(
            Order.created_at,
            created_from=created_from,
            created_to=created_to,
        )

    def _created_at_filters(
        self,
        column: Any,
        *,
        created_from: datetime | None,
        created_to: datetime | None,
    ) -> list[Any]:
        conditions: list[Any] = []
        if created_from is not None:
            conditions.append(column >= created_from)
        if created_to is not None:
            conditions.append(column <= created_to)
        return conditions
