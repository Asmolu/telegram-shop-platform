from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.pagination import PageMeta
from app.db.models import (
    BroadcastCampaignStatus,
    BroadcastCampaignType,
    BroadcastDeliveryStatus,
    NotificationChannel,
    NotificationTemplateCategory,
)

VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class NotificationTemplateBase(BaseModel):
    key: str = Field(..., min_length=2, max_length=150)
    name: str = Field(..., min_length=1, max_length=255)
    category: NotificationTemplateCategory
    channel: NotificationChannel = NotificationChannel.TELEGRAM
    title: str | None = Field(default=None, max_length=255)
    body_template: str = Field(..., min_length=1, max_length=4096)
    parse_mode: str | None = Field(default=None, max_length=32)
    allowed_variables: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("allowed_variables")
    @classmethod
    def validate_allowed_variables(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            variable = item.strip()
            if not VARIABLE_NAME_RE.fullmatch(variable):
                msg = f"Invalid template variable: {item}"
                raise ValueError(msg)
            if variable not in normalized:
                normalized.append(variable)
        return normalized


class NotificationTemplateCreate(NotificationTemplateBase):
    pass


class NotificationTemplateUpdate(BaseModel):
    key: str | None = Field(default=None, min_length=2, max_length=150)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: NotificationTemplateCategory | None = None
    title: str | None = Field(default=None, max_length=255)
    body_template: str | None = Field(default=None, min_length=1, max_length=4096)
    parse_mode: str | None = Field(default=None, max_length=32)
    allowed_variables: list[str] | None = None
    is_active: bool | None = None

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("allowed_variables")
    @classmethod
    def validate_allowed_variables(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return NotificationTemplateBase.validate_allowed_variables(value)


class NotificationTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    category: NotificationTemplateCategory
    channel: NotificationChannel
    title: str | None
    body_template: str
    parse_mode: str | None
    allowed_variables: list[str]
    is_active: bool
    created_by_user_id: int | None
    updated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class NotificationTemplateList(BaseModel):
    items: list[NotificationTemplateRead]
    meta: PageMeta


class BroadcastAudienceFilter(BaseModel):
    scope: Literal["all", "purchasers", "product", "category", "promo_code"] = "all"
    product_id: int | None = Field(default=None, ge=1)
    category_id: int | None = Field(default=None, ge=1)
    promo_code_id: int | None = Field(default=None, ge=1)


class BroadcastCampaignBase(BaseModel):
    template_id: int | None = Field(default=None, ge=1)
    name: str = Field(..., min_length=1, max_length=255)
    type: BroadcastCampaignType
    audience_filter: dict[str, Any] = Field(default_factory=lambda: {"scope": "all"})
    message_title: str | None = Field(default=None, max_length=255)
    message_body: str | None = Field(default=None, min_length=1, max_length=4096)
    parse_mode: str | None = Field(default=None, max_length=32)
    scheduled_at: datetime | None = None
    template_variables: dict[str, Any] = Field(default_factory=dict)


class BroadcastCampaignCreate(BroadcastCampaignBase):
    pass


class BroadcastCampaignUpdate(BaseModel):
    template_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: BroadcastCampaignType | None = None
    audience_filter: dict[str, Any] | None = None
    message_title: str | None = Field(default=None, max_length=255)
    message_body: str | None = Field(default=None, min_length=1, max_length=4096)
    parse_mode: str | None = Field(default=None, max_length=32)
    scheduled_at: datetime | None = None
    template_variables: dict[str, Any] | None = None


class BroadcastCampaignScheduleRequest(BaseModel):
    scheduled_at: datetime | None = None


class BroadcastCampaignTestRequest(BaseModel):
    message_suffix: str | None = Field(default=None, max_length=500)


class BroadcastCampaignProcessBatchRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=100)


class BroadcastCampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int | None
    name: str
    type: BroadcastCampaignType
    status: BroadcastCampaignStatus
    audience_filter: dict[str, Any]
    recipient_count_estimate: int
    recipient_count_final: int | None
    message_title: str | None
    message_body: str
    parse_mode: str | None
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by_user_id: int
    approved_by_user_id: int | None
    cancelled_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class BroadcastCampaignList(BaseModel):
    items: list[BroadcastCampaignRead]
    meta: PageMeta


class BroadcastDeliverySummary(BaseModel):
    pending: int = 0
    sending: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    blocked: int = 0
    rate_limited: int = 0
    total: int = 0


class BroadcastCampaignDetail(BaseModel):
    campaign: BroadcastCampaignRead
    delivery_summary: BroadcastDeliverySummary


class BroadcastCampaignPreview(BaseModel):
    campaign_id: int
    recipient_count_estimate: int
    rendered_sample: str
    eligibility_warnings: list[str]


class BroadcastCampaignTestResponse(BaseModel):
    ok: bool = True
    campaign_id: int
    telegram_message_id: int | None
    recipient_user_id: int | None
    recipient_username: str | None


class BroadcastCampaignProcessBatchResponse(BaseModel):
    campaign_id: int
    processed: int
    sent: int
    failed: int
    blocked: int
    rate_limited: int
    retried: int
    skipped: int
    remaining: int
    campaign_status: BroadcastCampaignStatus


class BroadcastDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    user_id: int | None
    subscription_id: int
    telegram_chat_id_masked: str
    status: BroadcastDeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None
    sent_at: datetime | None
    last_attempt_at: datetime | None
    telegram_message_id: int | None
    error_code: str | None
    error_message: str | None
    retry_after_seconds: int | None
    created_at: datetime
    updated_at: datetime


class BroadcastDeliveryList(BaseModel):
    items: list[BroadcastDeliveryRead]
    meta: PageMeta
