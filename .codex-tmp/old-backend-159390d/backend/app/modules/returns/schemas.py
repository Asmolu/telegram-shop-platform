from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.config import settings
from app.db.models import OrderStatus, ReturnRefundStatus, ReturnRequestStatus


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


class ReturnLifecycleCommentRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def trim_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class ReturnRefundProcessRequest(BaseModel):
    amount: Decimal | None = None
    currency: str = Field(default="RUB", min_length=1, max_length=3)
    method: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("amount must be greater than or equal to 0")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("currency is required")
        return normalized

    @field_validator("method", "comment")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class ReturnRestockItemProcessRequest(BaseModel):
    return_request_item_id: int = Field(gt=0)
    quantity: int = Field(ge=0)


class ReturnProcessRequest(BaseModel):
    refund: ReturnRefundProcessRequest | None = None
    restock_items: list[ReturnRestockItemProcessRequest] = Field(default_factory=list)
    complete: bool = True
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def trim_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @model_validator(mode="after")
    def reject_duplicate_restock_items(self) -> Self:
        item_ids = [item.return_request_item_id for item in self.restock_items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("duplicate return request items are not allowed")
        return self


class ReturnRefundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    return_request_id: int
    amount: Decimal
    currency: str
    method: str | None = None
    status: ReturnRefundStatus
    comment: str | None = None
    processed_at: datetime | None = None
    processed_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


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
    restocked_quantity: int = 0
    restocked_at: datetime | None = None
    restocked_by_user_id: int | None = None
    created_at: datetime

    @field_validator("restocked_quantity", mode="before")
    @classmethod
    def default_restocked_quantity(cls, value: int | None) -> int:
        return value or 0

    @computed_field
    @property
    def remaining_restockable_quantity(self) -> int:
        if self.product_variant_id is None:
            return 0
        return max(self.quantity - self.restocked_quantity, 0)

    @computed_field
    @property
    def can_restock(self) -> bool:
        return self.remaining_restockable_quantity > 0


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
    refund: ReturnRefundRead | None = None
    decided_at: datetime | None = None
    decided_by_user_id: int | None = None
    decision_comment: str | None = None
    completed_at: datetime | None = None
    completed_by_user_id: int | None = None
    completion_comment: str | None = None
    cancelled_at: datetime | None = None
    cancelled_by_user_id: int | None = None
    cancellation_comment: str | None = None
    message: str | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def total_return_amount(self) -> Decimal:
        return sum(
            (item.unit_price * item.quantity for item in self.items),
            Decimal("0.00"),
        )

    @computed_field
    @property
    def can_process(self) -> bool:
        return self.status == ReturnRequestStatus.APPROVED

    @computed_field
    @property
    def can_complete(self) -> bool:
        return self.status == ReturnRequestStatus.APPROVED


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
