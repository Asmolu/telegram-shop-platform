import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.pagination import PageMeta
from app.db.models import UserRole

TELEGRAM_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    phone: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserList(BaseModel):
    items: list[UserRead]
    meta: PageMeta


class UserBlockCreate(BaseModel):
    telegram_id: int | None = Field(default=None, gt=0)
    telegram_username: str | None = Field(default=None, max_length=33)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("telegram_username", mode="before")
    @classmethod
    def normalize_block_username(cls, value: object) -> object:
        return normalize_telegram_username(value)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_at_least_one_identifier(self) -> "UserBlockCreate":
        if self.telegram_id is None and self.telegram_username is None:
            raise ValueError("Telegram ID or username is required")
        return self


class UserBlockUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    telegram_username: str | None = None


class UserBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    telegram_id: int | None
    telegram_username: str | None
    reason: str | None
    blocked_at: datetime
    blocked_by_user_id: int | None
    unblocked_at: datetime | None
    unblocked_by_user_id: int | None
    user: UserBlockUserRead | None = None
    blocked_by: UserBlockUserRead | None = None


class UserBlockList(BaseModel):
    items: list[UserBlockRead]


class PersonalDataRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recipient_name: str | None = None
    contact_phone: str | None = None
    city: str | None = None
    height_cm: int | None = None
    weight_kg: float | None = None
    telegram_username: str | None = None
    persistent_comment: str | None = None


class PersonalDataUpdate(BaseModel):
    recipient_name: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=255)
    height_cm: int | None = Field(default=None, gt=0)
    weight_kg: float | None = Field(default=None, gt=0, le=9999.99)
    telegram_username: str | None = Field(default=None, max_length=33)
    persistent_comment: str | None = Field(default=None, max_length=500)

    @field_validator("recipient_name", "contact_phone", "city", "persistent_comment", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("contact_phone")
    @classmethod
    def validate_contact_phone(cls, value: str | None) -> str | None:
        if value is not None and not any(character.isdigit() for character in value):
            raise ValueError("Contact phone must contain at least one digit")
        return value

    @field_validator("telegram_username", mode="before")
    @classmethod
    def normalize_telegram_username(cls, value: object) -> object:
        return normalize_telegram_username(value)


def normalize_telegram_username(value: object) -> object:
    if not isinstance(value, str):
        return value
    username = value.strip().removeprefix("@").lower()
    if not username:
        return None
    if not TELEGRAM_USERNAME_RE.fullmatch(username):
        raise ValueError(
            "Telegram username must contain 5-32 Latin letters, digits, or underscores"
        )
    return username
