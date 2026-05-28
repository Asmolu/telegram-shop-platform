from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import OrderStatus


class OrderCheckoutCreate(BaseModel):
    contact_name: str = Field(min_length=1, max_length=255)
    contact_phone: str = Field(min_length=1, max_length=32)
    delivery_address: str = Field(min_length=1)
    delivery_comment: str | None = None
    promo_code: str | None = Field(default=None, min_length=1, max_length=64)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_variant_id: int
    product_name: str
    variant_size: str
    variant_sku: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    created_at: datetime


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    user_id: int
    status: OrderStatus
    subtotal_amount: Decimal
    discount_amount: Decimal
    promo_code_id: int | None = None
    promo_code_code: str | None = None
    total_amount: Decimal
    contact_name: str
    contact_phone: str
    delivery_address: str
    delivery_comment: str | None = None
    items: list[OrderItemRead]
    created_at: datetime
    updated_at: datetime


class OrderList(BaseModel):
    items: list[OrderRead]
