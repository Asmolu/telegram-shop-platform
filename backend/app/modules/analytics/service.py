from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageMeta
from app.core.config import settings
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
    TelemetryBatchIn,
    TelemetryEventIn,
    TelemetryIngestResult,
    TelemetryRetentionResult,
    TopBannerSummary,
    TopProductSummary,
    TopPromoCodeSummary,
)
from app.modules.products.search import sanitize_search_query

logger = logging.getLogger(__name__)
SELLER_TIMEZONE = ZoneInfo("Europe/Moscow")
TELEMETRY_ALWAYS_KEEP_EVENTS = {
    "auth.failed",
    "api.request_failed",
    "api.retry_exhausted",
    "checkout.failed",
    "checkout.ambiguous_outcome",
    "payment.submit_failed",
    "receipt.upload_failed",
    "chunk.load_failed",
    "chunk.recovery_failed",
    "frontend.error_boundary_triggered",
}
TELEMETRY_WEB_VITAL_EVENTS = {
    "web_vital.lcp",
    "web_vital.inp",
    "web_vital.cls",
    "web_vital.ttfb",
    "web_vital.fcp",
}
TELEMETRY_ROUTE_EVENTS = {
    "route.rendered",
    "first_product_card.rendered",
    "first_key_image.loaded",
}
TELEMETRY_NETWORK_EVENTS = {
    "api.retry_scheduled",
    "network.state_changed",
}


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

    async def ingest_telemetry(
        self,
        batch: TelemetryBatchIn,
        *,
        user_id: int | None,
        request_id: str | None,
    ) -> TelemetryIngestResult:
        if not settings.telemetry_enabled:
            return TelemetryIngestResult(accepted=0, sampled_out=len(batch.events))

        accepted = 0
        sampled_out = 0
        created_at = datetime.now(UTC)
        for payload in batch.events:
            if not should_keep_telemetry_event(payload):
                sampled_out += 1
                continue
            event = self._telemetry_event_from_payload(
                payload,
                user_id=user_id,
                request_id=request_id,
                created_at=created_at,
            )
            self.repository.add(event)
            accepted += 1

        if accepted:
            try:
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()
                logger.info(
                    "telemetry duplicate event ignored",
                    extra={"request_id": request_id},
                )
                return TelemetryIngestResult(accepted=0, sampled_out=sampled_out)
            except Exception:
                await self.session.rollback()
                logger.warning(
                    "telemetry storage failed",
                    extra={"request_id": request_id},
                )
                return TelemetryIngestResult(accepted=0, sampled_out=sampled_out)

        return TelemetryIngestResult(accepted=accepted, sampled_out=sampled_out)

    async def cleanup_telemetry(
        self,
        *,
        retention_days: int | None = None,
        batch_size: int | None = None,
        dry_run: bool = True,
    ) -> TelemetryRetentionResult:
        days = retention_days if retention_days is not None else settings.telemetry_retention_days
        limit = batch_size if batch_size is not None else settings.telemetry_cleanup_batch_size
        cutoff = datetime.now(UTC) - timedelta(days=days)
        matched = await self.repository.count_telemetry_before(cutoff)
        deleted = 0
        if not dry_run and matched:
            deleted = await self.repository.delete_telemetry_before(cutoff, limit=limit)
            await self.session.commit()
        logger.info(
            "telemetry retention cleanup summary",
            extra={"matched": matched, "deleted": deleted, "dry_run": dry_run},
        )
        return TelemetryRetentionResult(
            dry_run=dry_run,
            cutoff=cutoff,
            matched=matched,
            deleted=deleted,
        )

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

    def _telemetry_event_from_payload(
        self,
        payload: TelemetryEventIn,
        *,
        user_id: int | None,
        request_id: str | None,
        created_at: datetime,
    ) -> AnalyticsEvent:
        metadata = {
            key: value
            for key, value in {
                "telegram_webapp_version": payload.telegram_webapp_version,
                "theme_mode": payload.theme_mode,
                "save_data": payload.save_data,
                "retry_count": payload.retry_count,
                "success": payload.success,
                "response_size_bucket": payload.response_size_bucket,
                "payload_size_bucket": payload.payload_size_bucket,
                "viewport_class": payload.viewport_class,
                "device_class": payload.device_class,
                "idempotency_key_hash": payload.idempotency_key_hash,
            }.items()
            if value is not None
        }
        return AnalyticsEvent(
            event_name=payload.name,
            event_version=payload.version,
            telemetry_session_id=payload.session_id,
            client_event_id=payload.client_event_id,
            request_id=payload.request_id or request_id,
            route=payload.route,
            endpoint_scope=payload.endpoint_scope,
            http_method=payload.method,
            http_status=payload.status,
            duration_ms=payload.duration_ms,
            metric_value=payload.value,
            error_category=payload.error_category,
            platform=payload.platform,
            app_version=payload.app_version,
            network_state=payload.network_state,
            connection_type=payload.connection_type,
            user_id=user_id,
            event_metadata=metadata or None,
            created_at=created_at,
        )

    @staticmethod
    def _current_month_interval(now: datetime) -> tuple[datetime, datetime]:
        period_start = datetime(now.year, now.month, 1, tzinfo=SELLER_TIMEZONE)
        if now.month == 12:
            period_end = datetime(now.year + 1, 1, 1, tzinfo=SELLER_TIMEZONE)
        else:
            period_end = datetime(now.year, now.month + 1, 1, tzinfo=SELLER_TIMEZONE)
        return period_start, period_end


def should_keep_telemetry_event(event: TelemetryEventIn) -> bool:
    if event.name in TELEMETRY_ALWAYS_KEEP_EVENTS:
        return True
    if event.name == "api.request_completed" and event.method == "GET":
        return _deterministic_sample(
            event.session_id,
            event.name,
            event.endpoint_scope or "",
            rate=settings.telemetry_success_sample_rate,
        )
    if event.name in TELEMETRY_WEB_VITAL_EVENTS:
        if _is_poor_web_vital(event):
            return True
        return _deterministic_sample(
            event.session_id,
            event.name,
            rate=settings.telemetry_web_vital_sample_rate,
        )
    if event.name in TELEMETRY_ROUTE_EVENTS:
        return _deterministic_sample(
            event.session_id,
            event.name,
            event.route or "",
            rate=settings.telemetry_route_sample_rate,
        )
    if event.name in TELEMETRY_NETWORK_EVENTS:
        return _deterministic_sample(
            event.session_id,
            event.name,
            rate=settings.telemetry_network_sample_rate,
        )
    return True


def _deterministic_sample(*parts: str, rate: float) -> bool:
    if rate >= 1:
        return True
    if rate <= 0:
        return False
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket <= rate


def _is_poor_web_vital(event: TelemetryEventIn) -> bool:
    if event.value is None:
        return False
    thresholds = {
        "web_vital.lcp": 2500,
        "web_vital.inp": 200,
        "web_vital.cls": 0.1,
        "web_vital.ttfb": 800,
        "web_vital.fcp": 1800,
    }
    return event.value > thresholds.get(event.name, float("inf"))
