from datetime import datetime
from decimal import Decimal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable

from app.db.models import OrderStatus, ProductSizeGrid
from app.modules.manual_payments.schemas import ManualPaymentSummary


class OrderCheckoutCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    contact_name: str = Field(min_length=1, max_length=255)
    contact_phone: str = Field(min_length=1, max_length=32)
    delivery_address: str = Field(min_length=1)
    delivery_comment: str | None = None
    promo_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        validation_alias=AliasChoices("promo_code", "code"),
    )

    @field_validator("promo_code")
    @classmethod
    def normalize_promo_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().upper()


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_variant_id: int
    product_name: str
    variant_size: str
    variant_size_grid: ProductSizeGrid = ProductSizeGrid.CLOTHING_ALPHA
    variant_color: str | None = None
    variant_sku: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    product_thumbnail_path: str | None = None
    product_thumbnail_url: str | None = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def add_relation_derived_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            return data

        product = _loaded_relationship(data, "product")
        product_variant = _loaded_relationship(data, "product_variant")
        thumbnail_path, thumbnail_url = _product_thumbnail(product)
        variant_color = _read_attr(data, "variant_color")
        if variant_color is None and product_variant is not None:
            variant_color = _read_attr(product_variant, "color")

        return {
            "id": _read_attr(data, "id"),
            "product_id": _read_attr(data, "product_id"),
            "product_variant_id": _read_attr(data, "product_variant_id"),
            "product_name": _read_attr(data, "product_name"),
            "variant_size": _read_attr(data, "variant_size"),
            "variant_size_grid": (
                _read_attr(data, "variant_size_grid") or ProductSizeGrid.CLOTHING_ALPHA
            ),
            "variant_color": variant_color,
            "variant_sku": _read_attr(data, "variant_sku"),
            "unit_price": _read_attr(data, "unit_price"),
            "quantity": _read_attr(data, "quantity"),
            "subtotal": _read_attr(data, "subtotal"),
            "product_thumbnail_path": thumbnail_path,
            "product_thumbnail_url": thumbnail_url,
            "created_at": _read_attr(data, "created_at"),
        }

    @computed_field
    @property
    def product_title(self) -> str:
        return self.product_name

    @computed_field
    @property
    def item_total(self) -> Decimal:
        return self.subtotal


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
    manual_payment: ManualPaymentSummary | None = None
    items: list[OrderItemRead]
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def promo_code(self) -> str | None:
        return self.promo_code_code

    @computed_field
    @property
    def promo_applied(self) -> bool:
        return self.promo_code_id is not None and self.discount_amount > Decimal("0.00")

    @computed_field
    @property
    def subtotal(self) -> Decimal:
        return self.subtotal_amount

    @computed_field
    @property
    def discount(self) -> Decimal:
        return self.discount_amount

    @computed_field
    @property
    def total(self) -> Decimal:
        return self.total_amount


class OrderList(BaseModel):
    items: list[OrderRead]


def _loaded_relationship(instance: object | None, name: str) -> object | None:
    if instance is None:
        return None
    try:
        state = sa_inspect(instance)
        if name in state.unloaded:
            return None
    except NoInspectionAvailable:
        pass

    try:
        return getattr(instance, name)
    except Exception:
        return None


def _read_attr(instance: object, name: str) -> object | None:
    return getattr(instance, name, None)


def _product_thumbnail(product: object | None) -> tuple[str | None, str | None]:
    images = _loaded_relationship(product, "images")
    if not images:
        return None, None

    ordered_images = sorted(
        images,
        key=lambda image: (
            not bool(getattr(image, "is_primary", False)),
            getattr(image, "position", 0),
            getattr(image, "id", 0) or 0,
        ),
    )
    image = ordered_images[0]
    path = getattr(image, "file_path", None)
    if not path:
        return None, None
    return path, getattr(image, "url", f"/uploads/{path}")
