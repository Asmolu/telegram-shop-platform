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


class CartProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    base_price: Decimal
    size_grid: ProductSizeGrid
    status: ProductStatus


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
    unit_price: Decimal
    subtotal: Decimal
    created_at: datetime
    updated_at: datetime


class CartRead(BaseModel):
    id: int
    user_id: int
    items: list[CartItemRead]
    total: Decimal
    quantity_total: int
    distinct_item_count: int
    created_at: datetime
    updated_at: datetime
