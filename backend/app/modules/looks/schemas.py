from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.pagination import PageMeta
from app.db.models import (
    LookStatus,
    ProductImageBadgeColor,
    ProductImageBadgePosition,
    ProductImageBadgeType,
    ProductSizeGroup,
)
from app.modules.cart.schemas import CartRead
from app.modules.products.schemas import SLUG_PATTERN


class LookItemInput(BaseModel):
    product_id: int = Field(gt=0)
    position: int = Field(default=0, ge=0)
    quantity: int = Field(default=1, ge=1)
    is_default_selected: bool = True


class LookBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=SLUG_PATTERN)
    description: str | None = None
    status: LookStatus = LookStatus.DRAFT
    is_listed: bool = True
    search_priority: int = Field(default=1, ge=1, le=3)
    image_badge_type: ProductImageBadgeType = ProductImageBadgeType.NONE
    image_badge_text: str | None = Field(default=None, max_length=20)
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None

    @field_validator("title", "slug", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("image_badge_text")
    @classmethod
    def normalize_badge_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if "<" in normalized or ">" in normalized:
            raise ValueError("image_badge_text must not contain HTML")
        return normalized

    @model_validator(mode="after")
    def validate_badge(self) -> "LookBase":
        if self.image_badge_type == ProductImageBadgeType.CUSTOM and not self.image_badge_text:
            raise ValueError("image_badge_text is required for a custom badge")
        if self.image_badge_type != ProductImageBadgeType.CUSTOM:
            self.image_badge_text = None
        return self


class LookCreate(LookBase):
    items: list[LookItemInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_products(self) -> "LookCreate":
        _validate_unique_product_ids(self.items)
        return self


class LookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255, pattern=SLUG_PATTERN)
    description: str | None = None
    status: LookStatus | None = None
    is_listed: bool | None = None
    search_priority: int | None = Field(default=None, ge=1, le=3)
    image_badge_type: ProductImageBadgeType | None = None
    image_badge_text: str | None = Field(default=None, max_length=20)
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None
    items: list[LookItemInput] | None = None

    @field_validator("title", "slug", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("image_badge_text")
    @classmethod
    def normalize_badge_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_unique_products(self) -> "LookUpdate":
        if self.items is not None:
            _validate_unique_product_ids(self.items)
        return self


class LookImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    look_id: int
    file_path: str
    url: str
    image_url: str | None = None
    original_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    alt_text: str | None = None
    position: int
    is_primary: bool
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def fill_image_url(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        next_value = dict(value)
        next_value.setdefault("image_url", next_value.get("url"))
        return next_value


class LookAdminItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    look_id: int
    product_id: int
    position: int
    quantity: int
    is_default_selected: bool
    created_at: datetime
    updated_at: datetime


class LookAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    description: str | None = None
    status: LookStatus
    is_listed: bool
    search_priority: int
    image_badge_type: ProductImageBadgeType = ProductImageBadgeType.NONE
    image_badge_text: str | None = None
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None
    images: list[LookImageRead] = Field(default_factory=list)
    items: list[LookAdminItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("image_badge_type", mode="before")
    @classmethod
    def default_badge_type(cls, value: ProductImageBadgeType | None) -> ProductImageBadgeType:
        return value or ProductImageBadgeType.NONE


class LookAdminList(BaseModel):
    items: list[LookAdminRead]
    meta: PageMeta


class LookSlugList(BaseModel):
    items: list[str]


class LookProductSummaryRead(BaseModel):
    product_id: int
    product_slug: str
    name: str
    brand: str | None = None
    image_url: str | None = None
    price: Decimal
    old_price: Decimal | None = None


class LookPublicItemRead(BaseModel):
    look_item_id: int
    product: LookProductSummaryRead
    product_id: int
    product_slug: str
    product_name: str
    brand: str | None = None
    primary_image_url: str | None = None
    price: Decimal
    old_price: Decimal | None = None
    quantity: int
    is_default_selected: bool
    size_group: ProductSizeGroup
    available_sizes: list[str] = Field(default_factory=list)
    one_size: bool
    is_available: bool


class LookCardRead(BaseModel):
    id: int
    slug: str
    title: str
    description: str | None = None
    primary_image_url: str | None = None
    price: Decimal
    old_price: Decimal | None = None
    item_count: int
    image_badge_type: ProductImageBadgeType = ProductImageBadgeType.NONE
    image_badge_text: str | None = None
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None
    default_selected_item_ids: list[int] = Field(default_factory=list)
    is_available: bool
    available_sizes: list[str] = Field(default_factory=list)
    available_clothing_sizes: list[str] = Field(default_factory=list)
    available_footwear_sizes: list[str] = Field(default_factory=list)
    requires_clothing_size: bool = False
    requires_footwear_size: bool = False


class LookList(BaseModel):
    items: list[LookCardRead]
    meta: PageMeta


class LookDetailRead(BaseModel):
    id: int
    slug: str
    title: str
    description: str | None = None
    image_badge_type: ProductImageBadgeType = ProductImageBadgeType.NONE
    image_badge_text: str | None = None
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None
    images: list[LookImageRead] = Field(default_factory=list)
    items: list[LookPublicItemRead] = Field(default_factory=list)
    default_selected_item_ids: list[int] = Field(default_factory=list)
    default_price: Decimal
    old_price: Decimal | None = None
    available_sizes: list[str] = Field(default_factory=list)
    available_clothing_sizes: list[str] = Field(default_factory=list)
    available_footwear_sizes: list[str] = Field(default_factory=list)
    requires_clothing_size: bool = False
    requires_footwear_size: bool = False
    is_available: bool


class LookCartAddRequest(BaseModel):
    selected_item_ids: list[int] = Field(min_length=1)
    size: str | None = Field(default=None, min_length=1, max_length=64)
    clothing_size: str | None = Field(default=None, min_length=1, max_length=64)
    footwear_size: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("size", "clothing_size", "footwear_size", mode="before")
    @classmethod
    def normalize_size(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class LookCartAddResponse(BaseModel):
    message: str
    cart: CartRead


def _validate_unique_product_ids(items: list[LookItemInput]) -> None:
    product_ids = [item.product_id for item in items]
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("Product can be added to a Look only once")
