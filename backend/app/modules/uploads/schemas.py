from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UploadsStatus(BaseModel):
    module: str
    status: str


class ProductImageUploadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    file_path: str
    url: str
    original_filename: str | None
    mime_type: str | None
    size_bytes: int | None
    alt_text: str | None
    position: int
    is_primary: bool
    created_at: datetime


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
