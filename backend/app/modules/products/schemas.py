from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.pagination import PageMeta
from app.db.models import ProductSizeGrid, ProductStatus
from app.modules.categories.schemas import CategoryRead
from app.modules.products.inventory import InventoryValidationError, validate_inventory_quantities
from app.modules.products.search import (
    SEARCH_ALIAS_MAX_LENGTH,
    SEARCH_PRIORITY_DEFAULT,
    normalize_search_aliases,
)
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


class ProductCategoryInput(BaseModel):
    category_id: int = Field(gt=0)
    priority: int = Field(ge=1, le=3)


class ProductCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    priority: int
    category: CategoryRead | None = None


def _validate_category_assignments(
    categories: list[ProductCategoryInput] | None,
) -> list[ProductCategoryInput] | None:
    if categories is None:
        return None
    if len(categories) > 3:
        raise ValueError("products can have at most 3 categories")
    category_ids = [item.category_id for item in categories]
    if len(category_ids) != len(set(category_ids)):
        raise ValueError("duplicate product categories are not allowed")
    priorities = [item.priority for item in categories]
    if len(priorities) != len(set(priorities)):
        raise ValueError("product category priorities must be unique")
    return categories


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    base_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    old_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    search_priority: int = Field(
        default=SEARCH_PRIORITY_DEFAULT,
        ge=1,
        le=3,
        description="Default is 2 (medium). Lower numbers sort first in matching search results.",
    )
    search_aliases: str | None = Field(default=None, max_length=SEARCH_ALIAS_MAX_LENGTH)
    size_grid: ProductSizeGrid = ProductSizeGrid.CLOTHING_ALPHA
    status: ProductStatus = ProductStatus.DRAFT
    category_id: int | None = None

    @field_validator("search_aliases")
    @classmethod
    def normalize_aliases(cls, value: str | None) -> str | None:
        return normalize_search_aliases(value)

    @field_validator("search_priority", mode="before")
    @classmethod
    def default_search_priority(cls, value: int | None) -> int:
        return SEARCH_PRIORITY_DEFAULT if value is None else value

    @model_validator(mode="after")
    def validate_old_price(self) -> "ProductBase":
        if self.old_price is not None and self.old_price <= self.base_price:
            raise ValueError("old_price must be greater than base_price")
        return self


class ProductCreate(ProductBase):
    categories: list[ProductCategoryInput] | None = None
    tag_ids: list[int] = Field(default_factory=list)
    images: list[ProductImageCreate] = Field(default_factory=list)

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        value: list[ProductCategoryInput] | None,
    ) -> list[ProductCategoryInput] | None:
        return _validate_category_assignments(value)


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
    old_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    search_priority: int | None = Field(default=None, ge=1, le=3)
    search_aliases: str | None = Field(default=None, max_length=SEARCH_ALIAS_MAX_LENGTH)
    size_grid: ProductSizeGrid | None = None
    status: ProductStatus | None = None
    category_id: int | None = None
    categories: list[ProductCategoryInput] | None = None
    tag_ids: list[int] | None = None
    images: list[ProductImageCreate] | None = None

    @field_validator("search_aliases")
    @classmethod
    def normalize_aliases(cls, value: str | None) -> str | None:
        return normalize_search_aliases(value)

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        value: list[ProductCategoryInput] | None,
    ) -> list[ProductCategoryInput] | None:
        return _validate_category_assignments(value)

    @model_validator(mode="after")
    def validate_old_price_when_complete(self) -> "ProductUpdate":
        if (
            self.old_price is not None
            and self.base_price is not None
            and self.old_price <= self.base_price
        ):
            raise ValueError("old_price must be greater than base_price")
        return self


class ProductStatusUpdate(BaseModel):
    status: ProductStatus


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: CategoryRead | None
    categories: list[ProductCategoryRead] = Field(default_factory=list)
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
