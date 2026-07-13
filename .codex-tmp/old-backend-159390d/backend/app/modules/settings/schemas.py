from datetime import datetime
from urllib.parse import urlparse

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class PaymentSuccessBannerSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled: bool
    image_path: str | None = None
    image_url: str | None = None
    updated_at: datetime | None = None


class PaymentSuccessBannerSettingsUpdate(BaseModel):
    enabled: bool = False
    image_path: str | None = Field(
        default=None,
        max_length=1024,
        validation_alias=AliasChoices("image_path", "file_path"),
    )

    @field_validator("image_path")
    @classmethod
    def trim_image_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class SellerContactSettingsRead(BaseModel):
    telegram_url: str | None = None
    whatsapp_url: str | None = None
    instagram_url: str | None = None
    updated_at: datetime | None = None


class SellerContactSettingsUpdate(BaseModel):
    telegram_url: str | None = Field(default=None, max_length=1024)
    whatsapp_url: str | None = Field(default=None, max_length=1024)
    instagram_url: str | None = Field(default=None, max_length=1024)

    @field_validator("telegram_url", "whatsapp_url", "instagram_url")
    @classmethod
    def validate_optional_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        parsed = urlparse(trimmed)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Enter a full http(s) URL")
        return trimmed
