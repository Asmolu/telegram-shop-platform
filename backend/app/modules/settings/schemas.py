from datetime import datetime

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
