from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.config import settings
from app.db.models import (
    ManualPaymentCurrency,
    ManualPaymentMethod,
    ManualPaymentStatus,
    OrderDeliveryMethod,
    OrderStatus,
)


class SellerPaymentSettingsUpdate(BaseModel):
    is_manual_sbp_enabled: bool
    seller_phone: str | None = Field(default=None, max_length=64)
    seller_bank_name: str | None = Field(default=None, max_length=100)
    seller_recipient_name: str | None = Field(default=None, max_length=100)

    @field_validator("seller_phone", "seller_bank_name", "seller_recipient_name")
    @classmethod
    def trim_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class SellerPaymentSettingsRead(BaseModel):
    is_manual_sbp_enabled: bool
    seller_phone_e164: str | None = None
    seller_phone_display: str | None = None
    seller_bank_name: str | None = None
    seller_recipient_name: str | None = None
    updated_at: datetime | None = None


class ManualPaymentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ManualPaymentStatus
    expires_at: datetime
    submitted_at: datetime | None = None
    receipt_image_path: str | None = None

    @computed_field
    @property
    def receipt_image_url(self) -> str | None:
        return _receipt_image_url(self.receipt_image_path)


class ManualPaymentRead(BaseModel):
    id: int
    order_id: int
    order_number: str
    order_status: OrderStatus
    customer_user_id: int
    customer_name: str
    customer_phone: str
    delivery_method: OrderDeliveryMethod | None = None
    method: ManualPaymentMethod
    amount: Decimal
    currency: ManualPaymentCurrency
    status: ManualPaymentStatus
    expires_at: datetime
    server_now: datetime
    seller_phone_display: str
    seller_phone_e164: str
    seller_bank_name: str | None = None
    seller_recipient_name: str | None = None
    payment_comment: str
    receipt_image_path: str | None = None
    receipt_image_url: str | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    reject_reason: str | None = None
    stock_released_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ManualPaymentList(BaseModel):
    items: list[ManualPaymentRead]


class ManualPaymentReject(BaseModel):
    reject_reason: str | None = Field(default=None, max_length=500)

    @field_validator("reject_reason")
    @classmethod
    def trim_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class ManualPaymentExpireBatchRead(BaseModel):
    expired_count: int


def _receipt_image_url(receipt_image_path: str | None) -> str | None:
    if not receipt_image_path:
        return None
    return settings.public_upload_url_for(receipt_image_path)
