from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UploadsStatus(BaseModel):
    module: str
    status: str


class ProductImageUploadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    file_path: str
    url: str
    image_url: str | None = None
    thumbnail_path: str | None = None
    card_path: str | None = None
    detail_path: str | None = None
    thumbnail_url: str | None = None
    card_url: str | None = None
    detail_url: str | None = None
    image_variants: dict[str, str | None] = Field(default_factory=dict)
    original_filename: str | None
    mime_type: str | None
    size_bytes: int | None
    alt_text: str | None
    position: int
    is_primary: bool
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


class BannerImageUploadRead(BaseModel):
    file_path: str
    url: str
    original_filename: str
    mime_type: str
    size_bytes: int
    alt_text: str | None


class TagImageUploadRead(BaseModel):
    file_path: str
    url: str
    original_filename: str
    mime_type: str
    size_bytes: int
    alt_text: str | None


class CategoryImageUploadRead(BaseModel):
    file_path: str
    url: str
    original_filename: str
    mime_type: str
    size_bytes: int
    alt_text: str | None
