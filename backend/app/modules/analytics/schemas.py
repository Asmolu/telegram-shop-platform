from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.common.pagination import PageMeta


class AnalyticsEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    event_name: str
    user_id: int | None = None
    product_id: int | None = None
    order_id: int | None = None
    promo_code_id: int | None = None
    banner_id: int | None = None
    metadata: dict[str, Any] | None = Field(
        default=None,
        validation_alias=AliasChoices("event_metadata", "metadata"),
    )
    created_at: datetime


class AnalyticsEventList(BaseModel):
    items: list[AnalyticsEventRead]
    meta: PageMeta


class TopProductSummary(BaseModel):
    product_id: int
    product_name: str | None = None
    view_count: int


class TopPromoCodeSummary(BaseModel):
    promo_code_id: int
    promo_code: str | None = None
    used_count: int


class TopBannerSummary(BaseModel):
    banner_id: int
    banner_title: str | None = None
    click_count: int


class AnalyticsSummary(BaseModel):
    total_orders: int
    total_revenue: Decimal
    product_views_count: int
    cart_item_added_count: int
    checkout_started_count: int
    order_created_count: int
    promo_used_count: int
    banner_clicked_count: int
    top_products: list[TopProductSummary]
    top_promo_codes: list[TopPromoCodeSummary]
    top_banners: list[TopBannerSummary]
