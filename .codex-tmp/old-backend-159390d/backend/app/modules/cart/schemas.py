from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ProductSizeGrid, ProductStatus


class CartItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    product_variant_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class CartItemUpdate(BaseModel):
    quantity: int = Field(gt=0)


class CartItemSelectionUpdate(BaseModel):
    is_selected: bool


class CartSelectionUpdate(BaseModel):
    is_selected: bool
    item_ids: list[int] | None = None


class CartProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    brand: str | None = None
    base_price: Decimal
    old_price: Decimal | None = None
    size_grid: ProductSizeGrid
    status: ProductStatus
    image_url: str | None = None
    thumbnail_image_url: str | None = None


class CartProductVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    size: str
    color: str | None = None
    sku: str
    is_active: bool
    available_quantity: int


class CartItemRead(BaseModel):
    id: int
    product: CartProductRead
    product_variant: CartProductVariantRead
    quantity: int
    is_selected: bool
    unit_price: Decimal
    subtotal: Decimal
    source_type: str | None = None
    source_group_id: str | None = None
    source_look_id: int | None = None
    source_look_slug: str | None = None
    source_look_title: str | None = None
    source_look_image_url: str | None = None
    created_at: datetime
    updated_at: datetime


class CartRead(BaseModel):
    id: int
    user_id: int
    items: list[CartItemRead]
    total: Decimal
    quantity_total: int
    distinct_item_count: int
    selected_total: Decimal
    selected_quantity_total: int
    selected_distinct_item_count: int
    created_at: datetime
    updated_at: datetime
