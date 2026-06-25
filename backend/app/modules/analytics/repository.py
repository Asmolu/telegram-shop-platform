from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import String, and_, cast, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AnalyticsEvent,
    Banner,
    ManualPayment,
    ManualPaymentStatus,
    Order,
    OrderStatus,
    Product,
    ProductStatus,
    ProductVariant,
    PromoCode,
)

ACTIVE_ORDER_STATUSES = (
    OrderStatus.NEW,
    OrderStatus.PROCESSING,
    OrderStatus.SHIPPED,
)
PRODUCT_TOTAL_STATUSES = (
    ProductStatus.DRAFT,
    ProductStatus.ACTIVE,
    ProductStatus.OUT_OF_STOCK,
)
OUT_OF_STOCK_PRODUCT_STATUSES = (
    ProductStatus.ACTIVE,
    ProductStatus.OUT_OF_STOCK,
)
REVENUE_LEGACY_ORDER_STATUSES = (
    OrderStatus.PROCESSING,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
)


class AnalyticsRepository:
    """Database access layer for user behavior analytics."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, event: AnalyticsEvent) -> None:
        self.session.add(event)

    async def count_telemetry_before(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            select(func.count(AnalyticsEvent.id)).where(
                AnalyticsEvent.event_version.is_not(None),
                AnalyticsEvent.telemetry_session_id.is_not(None),
                AnalyticsEvent.created_at < cutoff,
            )
        )
        return result.scalar_one()

    async def delete_telemetry_before(self, cutoff: datetime, *, limit: int) -> int:
        ids = (
            select(AnalyticsEvent.id)
            .where(
                AnalyticsEvent.event_version.is_not(None),
                AnalyticsEvent.telemetry_session_id.is_not(None),
                AnalyticsEvent.created_at < cutoff,
            )
            .order_by(AnalyticsEvent.created_at.asc(), AnalyticsEvent.id.asc())
            .limit(limit)
            .subquery()
        )
        result = await self.session.execute(
            delete(AnalyticsEvent).where(AnalyticsEvent.id.in_(select(ids.c.id)))
        )
        return int(result.rowcount or 0)

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
            select(func.coalesce(func.sum(Order.total_amount), Decimal("0.00")))
            .join(ManualPayment, ManualPayment.order_id == Order.id, isouter=True)
            .where(
                *self._revenue_order_filters(
                    created_from=created_from,
                    created_to=created_to,
                )
            )
        )
        return result.scalar_one()

    async def count_active_orders(self) -> int:
        result = await self.session.execute(
            select(func.count(Order.id)).where(*self._active_order_filters())
        )
        return result.scalar_one()

    async def count_active_banners(self, *, now: datetime) -> int:
        result = await self.session.execute(
            select(func.count(Banner.id)).where(*self._active_banner_filters(now=now))
        )
        return result.scalar_one()

    async def count_products_total(self) -> int:
        result = await self.session.execute(
            select(func.count(Product.id)).where(*self._product_total_filters())
        )
        return result.scalar_one()

    async def count_products_out_of_stock(self) -> int:
        result = await self.session.execute(
            select(func.count(Product.id)).where(*self._out_of_stock_product_filters())
        )
        return result.scalar_one()

    async def revenue_for_orders(
        self,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> tuple[int, Decimal, Decimal, Decimal]:
        result = await self.session.execute(
            select(
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.subtotal_amount), Decimal("0.00")).label(
                    "gross_revenue"
                ),
                func.coalesce(func.sum(Order.discount_amount), Decimal("0.00")).label(
                    "discount_total"
                ),
                func.coalesce(func.sum(Order.total_amount), Decimal("0.00")).label(
                    "net_revenue"
                ),
            )
            .join(ManualPayment, ManualPayment.order_id == Order.id, isouter=True)
            .where(
                *self._revenue_order_filters(
                    created_from=period_start,
                    created_to=period_end,
                    end_exclusive=True,
                )
            )
        )
        row = result.one()
        return (
            int(row.orders_count),
            row.gross_revenue,
            row.discount_total,
            row.net_revenue,
        )

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

    def _revenue_order_filters(
        self,
        *,
        created_from: datetime | None,
        created_to: datetime | None,
        end_exclusive: bool = False,
    ) -> list[Any]:
        conditions = self._created_at_filters(
            Order.created_at,
            created_from=created_from,
            created_to=None if end_exclusive else created_to,
        )
        if created_to is not None and end_exclusive:
            conditions.append(Order.created_at < created_to)
        conditions.extend(
            [
                Order.status != OrderStatus.CANCELLED,
                or_(
                    and_(
                        ManualPayment.id.is_not(None),
                        ManualPayment.status == ManualPaymentStatus.APPROVED,
                    ),
                    and_(
                        ManualPayment.id.is_(None),
                        Order.status.in_(REVENUE_LEGACY_ORDER_STATUSES),
                    ),
                ),
            ]
        )
        return conditions

    def _active_order_filters(self) -> list[Any]:
        return [Order.status.in_(ACTIVE_ORDER_STATUSES)]

    def _active_banner_filters(self, *, now: datetime) -> list[Any]:
        return [
            Banner.is_active.is_(True),
            Banner.target_type.is_not(None),
            or_(Banner.starts_at.is_(None), Banner.starts_at <= now),
            or_(Banner.ends_at.is_(None), Banner.ends_at > now),
        ]

    def _product_total_filters(self) -> list[Any]:
        return [Product.status.in_(PRODUCT_TOTAL_STATUSES)]

    def _out_of_stock_product_filters(self) -> list[Any]:
        available_variant_exists = exists(
            select(ProductVariant.id).where(
                ProductVariant.product_id == Product.id,
                ProductVariant.is_active.is_(True),
                ProductVariant.stock_quantity > ProductVariant.reserved_quantity,
            )
        )
        return [
            Product.status.in_(OUT_OF_STOCK_PRODUCT_STATUSES),
            ~available_variant_exists,
        ]

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
