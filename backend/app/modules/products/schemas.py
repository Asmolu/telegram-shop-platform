from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMeta
from app.db.models import ProductStatus
from app.modules.categories.schemas import CategoryRead
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
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    items: list[ProductRead]
    meta: PageMeta
