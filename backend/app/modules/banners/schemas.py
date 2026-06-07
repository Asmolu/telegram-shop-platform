from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.pagination import PageMeta
from app.db.models import BannerDisplayType, BannerTargetType


class BannerBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=500)
    image_path: str = Field(min_length=1, max_length=1024)
    target_type: BannerTargetType
    target_id: int | None = Field(default=None, gt=0)
    external_url: str | None = Field(default=None, max_length=2048)
    display_type: BannerDisplayType = BannerDisplayType.HORIZONTAL
    position: int = Field(default=0, ge=0)
    is_active: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("external_url")
    @classmethod
    def normalize_external_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_target_and_dates(self) -> "BannerBase":
        if self.target_type == BannerTargetType.EXTERNAL_URL:
            if not self.external_url:
                raise ValueError("external_url is required for external_url banners")
        elif self.target_type in {BannerTargetType.PRODUCT, BannerTargetType.CATEGORY}:
            if self.target_id is None:
                raise ValueError("target_id is required for product and category banners")

        if self.starts_at is not None and self.ends_at is not None:
            if self.starts_at >= self.ends_at:
                raise ValueError("starts_at must be before ends_at")
        return self


class BannerCreate(BannerBase):
    pass


class BannerUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    subtitle: str | None = Field(default=None, max_length=500)
    image_path: str | None = Field(default=None, min_length=1, max_length=1024)
    target_type: BannerTargetType | None = None
    target_id: int | None = Field(default=None, gt=0)
    external_url: str | None = Field(default=None, max_length=2048)
    display_type: BannerDisplayType | None = None
    position: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("external_url")
    @classmethod
    def normalize_external_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class BannerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subtitle: str | None = None
    image_path: str
    image_url: str
    target_type: BannerTargetType | None = None
    target_id: int | None = None
    external_url: str | None = None
    display_type: BannerDisplayType = BannerDisplayType.HORIZONTAL
    position: int
    is_active: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("display_type", mode="before")
    @classmethod
    def default_display_type(
        cls,
        value: BannerDisplayType | str | None,
    ) -> BannerDisplayType | str:
        return value or BannerDisplayType.HORIZONTAL


class BannerList(BaseModel):
    items: list[BannerRead]
    meta: PageMeta


class BannerClickRead(BaseModel):
    banner_id: int
    event_name: str = "banner.clicked"
    tracked: bool = True
