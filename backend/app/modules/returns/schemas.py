from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.config import settings
from app.db.models import OrderStatus, ReturnRequestStatus


class ReturnRequestItemCreate(BaseModel):
    order_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class ReturnRequestCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    comment: str | None = Field(default=None, max_length=2000)
    items: list[ReturnRequestItemCreate] = Field(default_factory=list)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("reason is required")
        return trimmed

    @field_validator("comment")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @model_validator(mode="after")
    def reject_duplicate_items(self) -> Self:
        item_ids = [item.order_item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("duplicate order items are not allowed")
        return self


class ReturnDecisionRequest(BaseModel):
    decision_comment: str | None = Field(default=None, max_length=2000)

    @field_validator("decision_comment")
    @classmethod
    def trim_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class ReturnRequestItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_item_id: int
    product_id: int | None = None
    product_variant_id: int | None = None
    product_name: str
    product_brand: str | None = None
    sku: str | None = None
    size: str | None = None
    color: str | None = None
    unit_price: Decimal
    quantity: int
    created_at: datetime


class ReturnRequestAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    original_filename: str
    mime_type: str
    size_bytes: int
    media_type: str
    position: int
    created_at: datetime

    @computed_field
    @property
    def url(self) -> str:
        return settings.public_upload_url_for(self.file_path)


class ReturnRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    return_number: str
    order_id: int
    order_number: str | None = None
    order_status: OrderStatus | None = None
    user_id: int
    customer_name: str | None = None
    customer_phone: str | None = None
    status: ReturnRequestStatus
    reason: str
    comment: str | None = None
    items: list[ReturnRequestItemRead]
    attachments: list[ReturnRequestAttachmentRead]
    decided_at: datetime | None = None
    decided_by_user_id: int | None = None
    decision_comment: str | None = None
    message: str | None = None
    created_at: datetime
    updated_at: datetime


class ReturnRequestList(BaseModel):
    items: list[ReturnRequestRead]


class ReturnEligibilityItemRead(BaseModel):
    order_item_id: int
    product_name: str
    product_brand: str | None = None
    image_url: str | None = None
    sku: str | None = None
    size: str | None = None
    color: str | None = None
    quantity: int
    is_returnable: bool
    eligible: bool
    ineligible_reason: str | None = None


class ReturnEligibilityRead(BaseModel):
    eligible: bool
    reason_code: str | None = None
    message: str
    return_window_until: datetime | None = None
    order_id: int
    return_request_id: int | None = None
    items: list[ReturnEligibilityItemRead]
