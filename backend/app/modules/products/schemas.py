from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.pagination import PageMeta
from app.db.models import ProductStatus
from app.modules.categories.schemas import CategoryRead
from app.modules.products.inventory import InventoryValidationError, validate_inventory_quantities
from app.modules.tags.schemas import TagRead


class ProductImageBase(BaseModel):
    file_path: str = Field(min_length=1, max_length=1024)
    alt_text: str | None = Field(default=None, max_length=255)
    position: int = Field(default=0, ge=0)
    is_primary: bool = False


class ProductImageCreate(ProductImageBase):
    pass


class ProductImageRead(ProductImageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    url: str
    original_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime


class ProductVariantBase(BaseModel):
    size: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=100)
    stock_quantity: int = Field(default=0, ge=0)
    reserved_quantity: int = Field(default=0, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_inventory(self) -> "ProductVariantBase":
        try:
            validate_inventory_quantities(self.stock_quantity, self.reserved_quantity)
        except InventoryValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantUpdate(BaseModel):
    size: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, min_length=1, max_length=64)
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    stock_quantity: int | None = Field(default=None, ge=0)
    reserved_quantity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_inventory_when_complete(self) -> "ProductVariantUpdate":
        if self.stock_quantity is None or self.reserved_quantity is None:
            return self
        try:
            validate_inventory_quantities(self.stock_quantity, self.reserved_quantity)
        except InventoryValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class ProductVariantRead(ProductVariantBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    available_quantity: int
    created_at: datetime
    updated_at: datetime


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    base_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    status: ProductStatus = ProductStatus.DRAFT
    category_id: int | None = None


class ProductCreate(ProductBase):
    tag_ids: list[int] = Field(default_factory=list)
    images: list[ProductImageCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = None
    base_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    status: ProductStatus | None = None
    category_id: int | None = None
    tag_ids: list[int] | None = None
    images: list[ProductImageCreate] | None = None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: CategoryRead | None
    tags: list[TagRead]
    images: list[ProductImageRead]
    variants: list[ProductVariantRead] = Field(default_factory=list)
    is_available: bool = False
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    items: list[ProductRead]
    meta: PageMeta


class ProductVariantList(BaseModel):
    items: list[ProductVariantRead]
