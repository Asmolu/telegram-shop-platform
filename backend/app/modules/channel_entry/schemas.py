from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.pagination import PageMeta

MAX_CHANNEL_ENTRY_PHOTOS = 4
ButtonStyle = Literal["default", "primary", "secondary", "danger", "success"]

DEFAULT_BUTTON_TEXT = "Открыть"


class ChannelEntryConfigRead(BaseModel):
    bot_username: str
    mini_app_direct_url: str
    mini_app_url: str
    start_param: str
    short_name: str
    has_customer_bot_token: bool
    setup_hint: str


class TelegramChannelBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    chat_id: str = Field(min_length=1, max_length=255)

    @field_validator("title", "chat_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class TelegramChannelCreate(TelegramChannelBase):
    pass


class TelegramChannelUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    chat_id: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None

    @field_validator("title", "chat_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class TelegramChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    chat_id: str
    is_active: bool
    last_checked_at: datetime | None
    last_check_status: str | None
    last_check_error: str | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class ChannelCheckRequest(BaseModel):
    chat_id: str = Field(min_length=1, max_length=255)

    @field_validator("chat_id")
    @classmethod
    def strip_chat_id(cls, value: str) -> str:
        return value.strip()


class ChannelCheckResponse(BaseModel):
    ok: bool
    chat_id: str
    title: str | None = None
    type: str | None = None
    username: str | None = None
    can_post_estimate: bool | None = None
    can_pin_estimate: bool | None = None
    message: str


class ChannelEntryPreviewRequest(BaseModel):
    channel_id: int | None = Field(default=None, gt=0)
    chat_id: str | None = Field(default=None, min_length=1, max_length=255)
    text: str = Field(default="", max_length=4096)
    button_text: str = Field(default=DEFAULT_BUTTON_TEXT, min_length=1, max_length=64)
    button_style: ButtonStyle = "default"
    photo_paths: list[str] = Field(default_factory=list, max_length=MAX_CHANNEL_ENTRY_PHOTOS)

    @field_validator("chat_id", "text", "button_text")
    @classmethod
    def strip_optional_or_required_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("photo_paths")
    @classmethod
    def strip_photo_paths(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_text_and_photos(self) -> "ChannelEntryPreviewRequest":
        if not self.text and not self.photo_paths:
            raise ValueError("Text is required when no photo is attached")
        if self.photo_paths and len(self.text) > 1024:
            raise ValueError("Caption must be 1024 characters or shorter when photos are attached")
        return self


class ChannelEntryPreviewRead(BaseModel):
    text: str
    button_text: str
    button_style: ButtonStyle
    button_url: str
    photo_paths: list[str]
    photo_urls: list[str]
    selected_chat_id: str
    warnings: list[str]


class ChannelEntryPublishRequest(ChannelEntryPreviewRequest):
    pin: bool = True
    disable_notification: bool = False


class TelegramChannelEntryMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int | None
    channel: TelegramChannelRead | None = None
    chat_id: str
    text: str
    button_text: str
    button_url: str
    telegram_message_id: int | None
    is_pinned: bool
    published_at: datetime | None
    pinned_at: datetime | None
    last_error: str | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class ChannelEntryPublishRead(BaseModel):
    ok: bool
    status: str
    message: str
    item: TelegramChannelEntryMessageRead


class ChannelEntryHistoryRead(BaseModel):
    items: list[TelegramChannelEntryMessageRead]
    meta: PageMeta
