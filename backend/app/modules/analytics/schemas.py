from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.common.pagination import PageMeta


class AnalyticsEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    event_name: str
    event_version: int | None = None
    telemetry_session_id: str | None = None
    client_event_id: str | None = None
    request_id: str | None = None
    route: str | None = None
    endpoint_scope: str | None = None
    http_method: str | None = None
    http_status: int | None = None
    duration_ms: int | None = None
    metric_value: float | None = None
    error_category: str | None = None
    platform: str | None = None
    app_version: str | None = None
    network_state: str | None = None
    connection_type: str | None = None
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


class DashboardRevenueMonth(BaseModel):
    period_start: datetime
    period_end: datetime
    orders_count: int
    gross_revenue: Decimal
    discount_total: Decimal
    net_revenue: Decimal


class DashboardSummary(BaseModel):
    active_orders_count: int
    active_banners_count: int
    products_total: int
    products_out_of_stock: int
    revenue_month: DashboardRevenueMonth


TelemetryEventName = Literal[
    "mini_app.bootstrap_started",
    "mini_app.bootstrap_completed",
    "telegram.initialized",
    "auth.started",
    "auth.completed",
    "auth.failed",
    "route.rendered",
    "first_product_card.rendered",
    "first_key_image.loaded",
    "web_vital.lcp",
    "web_vital.inp",
    "web_vital.cls",
    "web_vital.ttfb",
    "web_vital.fcp",
    "api.request_completed",
    "api.request_failed",
    "api.retry_scheduled",
    "api.retry_exhausted",
    "network.state_changed",
    "checkout.started",
    "checkout.completed",
    "checkout.failed",
    "checkout.ambiguous_outcome",
    "payment.submit_started",
    "payment.submit_completed",
    "payment.submit_failed",
    "receipt.prepare_completed",
    "receipt.upload_completed",
    "receipt.upload_failed",
    "chunk.load_failed",
    "chunk.reload_attempted",
    "chunk.recovery_failed",
    "frontend.error_boundary_triggered",
]

TelemetryPlatform = Literal["ios", "android", "web", "tdesktop", "unknown"]
TelemetryThemeMode = Literal["light", "dark", "auto", "unknown"]
TelemetryNetworkState = Literal["online", "slow", "offline", "recovering", "unknown"]
TelemetryConnectionType = Literal["slow-2g", "2g", "3g", "4g", "unknown"]
TelemetryErrorCategory = Literal[
    "authentication",
    "validation",
    "network_unavailable",
    "timeout",
    "request_aborted",
    "rate_limited",
    "temporary_server_failure",
    "permanent_server_failure",
    "chunk_load_failed",
    "render_error",
    "unknown",
]
TelemetryByteBucket = Literal["unknown", "0", "1kb", "10kb", "100kb", "1mb", "large"]
TelemetryViewportClass = Literal["small", "medium", "large", "unknown"]
TelemetryDeviceClass = Literal["mobile", "tablet", "desktop", "unknown"]


class TelemetryEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: TelemetryEventName
    version: Literal[1] = 1
    session_id: Annotated[str, Field(min_length=16, max_length=64)]
    client_event_id: Annotated[str | None, Field(min_length=8, max_length=64)] = None
    route: Annotated[str | None, Field(max_length=160)] = None
    platform: TelemetryPlatform | None = None
    telegram_webapp_version: Annotated[str | None, Field(max_length=32)] = None
    theme_mode: TelemetryThemeMode | None = None
    network_state: TelemetryNetworkState | None = None
    connection_type: TelemetryConnectionType | None = None
    save_data: bool | None = None
    duration_ms: Annotated[int | None, Field(ge=0, le=300_000)] = None
    value: Annotated[float | None, Field(ge=0, le=10_000_000)] = None
    method: Annotated[str | None, Field(max_length=10)] = None
    endpoint_scope: Annotated[str | None, Field(max_length=160)] = None
    status: Annotated[int | None, Field(ge=0, le=599)] = None
    retry_count: Annotated[int | None, Field(ge=0, le=10)] = None
    error_category: TelemetryErrorCategory | None = None
    request_id: Annotated[str | None, Field(max_length=64)] = None
    app_version: Annotated[str | None, Field(max_length=80)] = None
    success: bool | None = None
    response_size_bucket: TelemetryByteBucket | None = None
    payload_size_bucket: TelemetryByteBucket | None = None
    viewport_class: TelemetryViewportClass | None = None
    device_class: TelemetryDeviceClass | None = None
    idempotency_key_hash: Annotated[str | None, Field(min_length=8, max_length=24)] = None

    @field_validator("route")
    @classmethod
    def validate_route(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if "?" in value or "#" in value:
            msg = "route must not contain query or hash"
            raise ValueError(msg)
        if not value.startswith("/"):
            msg = "route must start with /"
            raise ValueError(msg)
        return value

    @field_validator("endpoint_scope")
    @classmethod
    def validate_endpoint_scope(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if "?" in value or "#" in value:
            msg = "endpoint_scope must not contain query or hash"
            raise ValueError(msg)
        parts = [part for part in value.split("/") if part]
        if any(part.isdigit() for part in parts):
            msg = "endpoint_scope must not contain raw ids"
            raise ValueError(msg)
        return value if value.startswith("/") else f"/{value}"

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class TelemetryBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: Annotated[list[TelemetryEventIn], Field(min_length=1, max_length=25)]


class TelemetryIngestResult(BaseModel):
    accepted: int
    sampled_out: int


class TelemetryRetentionResult(BaseModel):
    dry_run: bool
    cutoff: datetime
    matched: int
    deleted: int
