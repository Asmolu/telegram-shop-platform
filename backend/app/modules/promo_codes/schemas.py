from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.pagination import PageMeta
from app.db.models import DiscountType


class PromoCodeBase(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    discount_type: DiscountType
    discount_value: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    is_active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int | None = Field(default=None, gt=0)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_discount_and_dates(self) -> "PromoCodeBase":
        if self.discount_type == DiscountType.PERCENT and self.discount_value > Decimal("100"):
            raise ValueError("Percentage discount cannot exceed 100")
        has_date_range = self.starts_at is not None and self.ends_at is not None
        if has_date_range and self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        return self


class PromoCodeCreate(PromoCodeBase):
    pass


class PromoCodeUpdate(BaseModel):
    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    is_active: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int | None = Field(default=None, gt=0)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()


class PromoCodeRead(PromoCodeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PromoCodeList(BaseModel):
    items: list[PromoCodeRead]
    meta: PageMeta


class PromoCodeValidateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class PromoCodeValidationRead(BaseModel):
    code: str
    discount_type: DiscountType
    discount_value: Decimal
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
