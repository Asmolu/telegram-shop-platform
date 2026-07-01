from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.pagination import PageMeta
from app.db.models import (
    ProductImageBadgeColor,
    ProductImageBadgePosition,
    ProductImageBadgeType,
    ProductSizeGrid,
    ProductStatus,
)
from app.modules.categories.schemas import CategoryRead
from app.modules.products.inventory import InventoryValidationError, validate_inventory_quantities
from app.modules.products.search import (
    SEARCH_ALIAS_MAX_LENGTH,
    SEARCH_PRIORITY_DEFAULT,
    SearchSuggestionKind,
    normalize_search_aliases,
)
from app.modules.tags.schemas import TagRead

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class ProductImageBase(BaseModel):
    file_path: str = Field(min_length=1, max_length=1024)
    alt_text: str | None = Field(default=None, max_length=255)
    position: int = Field(default=0, ge=0)
    is_primary: bool = False


class ProductImageCreate(ProductImageBase):
    pass


class ProductImageVariants(BaseModel):
    thumbnail: str | None = None
    card: str | None = None
    detail: str | None = None


class ProductImageRead(ProductImageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    url: str
    image_url: str | None = None
    thumbnail_path: str | None = None
    card_path: str | None = None
    detail_path: str | None = None
    thumbnail_url: str | None = None
    card_url: str | None = None
    detail_url: str | None = None
    image_variants: ProductImageVariants = Field(default_factory=ProductImageVariants)
    original_filename: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def fill_compatible_image_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        next_value = dict(value)
        next_value.setdefault("image_url", next_value.get("url"))
        next_value.setdefault(
            "image_variants",
            {
                "thumbnail": next_value.get("thumbnail_url"),
                "card": next_value.get("card_url"),
                "detail": next_value.get("detail_url"),
            },
        )
        return next_value


class PublicTaxonomyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None = None
    image_url: str | None = None


class ProductPublicImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    image_url: str | None = None
    thumbnail_url: str | None = None
    card_url: str | None = None
    detail_url: str | None = None
    image_variants: ProductImageVariants = Field(default_factory=ProductImageVariants)
    alt_text: str | None = None
    position: int
    is_primary: bool

    @model_validator(mode="before")
    @classmethod
    def fill_compatible_image_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        next_value = dict(value)
        next_value.setdefault("image_url", next_value.get("url"))
        next_value.setdefault(
            "image_variants",
            {
                "thumbnail": next_value.get("thumbnail_url"),
                "card": next_value.get("card_url"),
                "detail": next_value.get("detail_url"),
            },
        )
        return next_value


class ProductVariantBase(BaseModel):
    size: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=100)
    stock_quantity: int = Field(default=0, ge=0)
    reserved_quantity: int = Field(default=0, ge=0)
    is_active: bool = True

    @field_validator("color", mode="before")
    @classmethod
    def normalize_color(cls, value: object) -> object:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_inventory(self) -> "ProductVariantBase":
        try:
            validate_inventory_quantities(self.stock_quantity, self.reserved_quantity)
        except InventoryValidationError as exc:
            raise ValueError(str(exc)) from exc
        return self


class ProductVariantCreate(ProductVariantBase):
    sku: str | None = Field(default=None, min_length=1, max_length=100)


class ProductVariantUpdate(BaseModel):
    size: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, min_length=1, max_length=64)
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    stock_quantity: int | None = Field(default=None, ge=0)
    reserved_quantity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("color", mode="before")
    @classmethod
    def normalize_color(cls, value: object) -> object:
        return _normalize_optional_text(value)

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


class ProductCardVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    size: str
    color: str | None = None
    available_quantity: int
    is_active: bool


class ProductPublicVariantRead(ProductCardVariantRead):
    sku: str


class ProductCategoryInput(BaseModel):
    category_id: int = Field(gt=0)
    priority: int = Field(ge=1, le=3)


class ProductCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    priority: int
    category: CategoryRead | None = None


class ProductPublicCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    priority: int
    category: PublicTaxonomyRead | None = None


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


def _validate_related_product_ids(product_ids: list[int] | None) -> list[int] | None:
    if product_ids is None:
        return None
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("duplicate related product IDs are not allowed")
    return product_ids


def _normalize_badge_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if "<" in normalized or ">" in normalized:
        raise ValueError("image_badge_text must not contain HTML")
    return normalized


def _normalize_optional_text(value: object) -> object:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    return normalized or None


def _normalize_optional_enum(value: object) -> object:
    return _normalize_optional_text(value)


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=SLUG_PATTERN)
    brand: str | None = Field(default=None, min_length=1, max_length=120)
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
    image_badge_type: ProductImageBadgeType = ProductImageBadgeType.NONE
    image_badge_text: str | None = Field(default=None, max_length=20)
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None
    status: ProductStatus = ProductStatus.DRAFT
    is_listed: bool = True
    is_returnable: bool = True
    category_id: int | None = None

    @field_validator("search_aliases")
    @classmethod
    def normalize_aliases(cls, value: str | None) -> str | None:
        return normalize_search_aliases(value)

    @field_validator("brand", mode="before")
    @classmethod
    def normalize_brand(cls, value: object) -> object:
        return _normalize_optional_text(value)

    @field_validator("search_priority", mode="before")
    @classmethod
    def default_search_priority(cls, value: int | None) -> int:
        return SEARCH_PRIORITY_DEFAULT if value is None else value

    @field_validator("image_badge_type", mode="before")
    @classmethod
    def default_image_badge_type(
        cls,
        value: ProductImageBadgeType | None,
    ) -> ProductImageBadgeType:
        return ProductImageBadgeType.NONE if value is None else value

    @field_validator("image_badge_color", "image_badge_position", mode="before")
    @classmethod
    def normalize_optional_badge_enum(cls, value: object) -> object:
        return _normalize_optional_enum(value)

    @field_validator("image_badge_text")
    @classmethod
    def normalize_badge_text(cls, value: str | None) -> str | None:
        return _normalize_badge_text(value)

    @model_validator(mode="after")
    def validate_old_price(self) -> "ProductBase":
        if self.old_price is not None and self.old_price <= self.base_price:
            raise ValueError("old_price must be greater than base_price")
        if self.image_badge_type == ProductImageBadgeType.CUSTOM and not self.image_badge_text:
            raise ValueError("image_badge_text is required for a custom badge")
        if self.image_badge_type != ProductImageBadgeType.CUSTOM:
            self.image_badge_text = None
        return self


class ProductCreate(ProductBase):
    slug: str | None = Field(default=None, min_length=1, max_length=255, pattern=SLUG_PATTERN)
    categories: list[ProductCategoryInput] | None = None
    tag_ids: list[int] = Field(default_factory=list)
    images: list[ProductImageCreate] = Field(default_factory=list)
    related_product_ids: list[int] = Field(default_factory=list)

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_blank_slug(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        value: list[ProductCategoryInput] | None,
    ) -> list[ProductCategoryInput] | None:
        return _validate_category_assignments(value)

    @field_validator("related_product_ids")
    @classmethod
    def validate_related_product_ids(cls, value: list[int]) -> list[int]:
        return _validate_related_product_ids(value) or []


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=SLUG_PATTERN,
    )
    brand: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    base_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    old_price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    search_priority: int | None = Field(default=None, ge=1, le=3)
    search_aliases: str | None = Field(default=None, max_length=SEARCH_ALIAS_MAX_LENGTH)
    size_grid: ProductSizeGrid | None = None
    image_badge_type: ProductImageBadgeType | None = None
    image_badge_text: str | None = Field(default=None, max_length=20)
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None
    status: ProductStatus | None = None
    is_listed: bool | None = None
    is_returnable: bool | None = None
    category_id: int | None = None
    categories: list[ProductCategoryInput] | None = None
    tag_ids: list[int] | None = None
    images: list[ProductImageCreate] | None = None
    related_product_ids: list[int] | None = None

    @field_validator("search_aliases")
    @classmethod
    def normalize_aliases(cls, value: str | None) -> str | None:
        return normalize_search_aliases(value)

    @field_validator("brand", mode="before")
    @classmethod
    def normalize_brand(cls, value: object) -> object:
        return _normalize_optional_text(value)

    @field_validator("image_badge_color", "image_badge_position", mode="before")
    @classmethod
    def normalize_optional_badge_enum(cls, value: object) -> object:
        return _normalize_optional_enum(value)

    @field_validator("image_badge_text")
    @classmethod
    def normalize_badge_text(cls, value: str | None) -> str | None:
        return _normalize_badge_text(value)

    @field_validator("categories")
    @classmethod
    def validate_categories(
        cls,
        value: list[ProductCategoryInput] | None,
    ) -> list[ProductCategoryInput] | None:
        return _validate_category_assignments(value)

    @field_validator("related_product_ids")
    @classmethod
    def validate_related_product_ids(cls, value: list[int] | None) -> list[int] | None:
        return _validate_related_product_ids(value)

    @model_validator(mode="after")
    def validate_old_price_when_complete(self) -> "ProductUpdate":
        if (
            self.old_price is not None
            and self.base_price is not None
            and self.old_price <= self.base_price
        ):
            raise ValueError("old_price must be greater than base_price")
        if (
            self.image_badge_type == ProductImageBadgeType.CUSTOM
            and "image_badge_text" in self.model_fields_set
            and not self.image_badge_text
        ):
            raise ValueError("image_badge_text is required for a custom badge")
        return self


class ProductStatusUpdate(BaseModel):
    status: ProductStatus


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: CategoryRead | None
    categories: list[ProductPublicCategoryRead] = Field(default_factory=list)
    tags: list[TagRead]
    images: list[ProductImageRead]
    variants: list[ProductVariantRead] = Field(default_factory=list)
    is_available: bool = False
    created_at: datetime
    updated_at: datetime


class ProductDetailRead(ProductRead):
    related_product_ids: list[int] = Field(default_factory=list)
    related_products: list[ProductRead] = Field(default_factory=list)


class ProductList(BaseModel):
    items: list[ProductRead]
    meta: PageMeta


class ProductCardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    brand: str | None = None
    base_price: Decimal
    old_price: Decimal | None = None
    size_grid: ProductSizeGrid
    image_badge_type: ProductImageBadgeType = ProductImageBadgeType.NONE
    image_badge_text: str | None = None
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None
    image_url: str | None = None
    thumbnail_image_url: str | None = None
    image_width: int | None = 480
    image_height: int | None = 600
    variants: list[ProductCardVariantRead] = Field(default_factory=list)
    is_available: bool = False
    created_at: datetime


class ProductCardList(BaseModel):
    items: list[ProductCardRead]
    meta: PageMeta


class ProductPublicDetailRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    brand: str | None = None
    description: str | None = None
    base_price: Decimal
    old_price: Decimal | None = None
    size_grid: ProductSizeGrid
    image_badge_type: ProductImageBadgeType = ProductImageBadgeType.NONE
    image_badge_text: str | None = None
    image_badge_color: ProductImageBadgeColor | None = None
    image_badge_position: ProductImageBadgePosition | None = None
    category: PublicTaxonomyRead | None = None
    categories: list[ProductCategoryRead] = Field(default_factory=list)
    tags: list[PublicTaxonomyRead] = Field(default_factory=list)
    images: list[ProductPublicImageRead] = Field(default_factory=list)
    variants: list[ProductPublicVariantRead] = Field(default_factory=list)
    related_product_ids: list[int] = Field(default_factory=list)
    related_products: list[ProductCardRead] = Field(default_factory=list)
    is_available: bool = False
    created_at: datetime


ProductResolveVariantStatus = Literal[
    "selected",
    "out_of_stock",
    "sku_missing",
    "sku_not_found",
    "sku_not_for_product",
    "inactive",
]


class ProductResolveRouteCategory(BaseModel):
    id: int
    slug: str
    name: str


class ProductResolveRouteContext(BaseModel):
    category: ProductResolveRouteCategory | None = None
    product_slug: str
    requested_sku: str | None = None
    selected_variant_id: int | None = None
    selected_variant_sku: str | None = None
    variant_status: ProductResolveVariantStatus | None = None


class ProductResolveResponse(BaseModel):
    product: ProductPublicDetailRead
    route_context: ProductResolveRouteContext


class ProductVariantList(BaseModel):
    items: list[ProductVariantRead]


class ProductVariantSkuList(BaseModel):
    items: list[str]


class ProductSlugList(BaseModel):
    items: list[str]


class ProductSearchSuggestion(BaseModel):
    value: str
    kind: SearchSuggestionKind
    label: str | None = None


class ProductSearchSuggestionList(BaseModel):
    items: list[ProductSearchSuggestion]
