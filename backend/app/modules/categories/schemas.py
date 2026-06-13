from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

CATEGORY_IMAGE_PATH_PATTERN = r"^categories/[0-9a-f]{32}\.(?:jpg|jpeg|png|webp)$"


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    image_path: str | None = Field(
        default=None,
        max_length=1024,
        pattern=CATEGORY_IMAGE_PATH_PATTERN,
    )


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = None
    image_path: str | None = Field(
        default=None,
        max_length=1024,
        pattern=CATEGORY_IMAGE_PATH_PATTERN,
    )


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime
