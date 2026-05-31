import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.users.schemas import UserRead

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TELEGRAM_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


class SellerRegistrationStartRequest(BaseModel):
    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    telegram_username: str = Field(..., min_length=5, max_length=33)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not EMAIL_RE.match(email):
            raise ValueError("Enter a valid email address")
        return email

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain at least one letter and one digit")
        return value

    @field_validator("telegram_username")
    @classmethod
    def validate_telegram_username(cls, value: str) -> str:
        username = normalize_telegram_username(value)
        if username is None:
            raise ValueError("Enter a valid Telegram username")
        return username


class SellerRegistrationStartResponse(BaseModel):
    registration_id: int
    bot_start_link: str | None
    start_command: str
    expires_at: datetime


class SellerTelegramStartRequest(BaseModel):
    start_payload: str = Field(..., min_length=8, max_length=128)
    telegram_user_id: int = Field(..., gt=0)
    telegram_chat_id: int = Field(..., gt=0)
    telegram_username: str | None = Field(default=None, max_length=33)

    @field_validator("telegram_username")
    @classmethod
    def validate_optional_telegram_username(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        username = normalize_telegram_username(value)
        if username is None:
            raise ValueError("Enter a valid Telegram username")
        return username


class SellerTelegramStartResponse(BaseModel):
    registration_id: int
    telegram_username: str | None
    verification_expires_at: datetime


class SellerRegistrationConfirmRequest(BaseModel):
    registration_id: int = Field(..., gt=0)
    code: str = Field(..., min_length=4, max_length=12)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        code = value.strip()
        if not code.isdigit():
            raise ValueError("Verification code must contain digits only")
        return code


class SellerRegistrationResendCodeRequest(BaseModel):
    registration_id: int = Field(..., gt=0)


class SellerRegistrationResendCodeResponse(BaseModel):
    registration_id: int
    verification_expires_at: datetime


class SellerLoginRequest(BaseModel):
    email: str = Field(..., max_length=320)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not EMAIL_RE.match(email):
            raise ValueError("Enter a valid email address")
        return email


class SellerMeResponse(UserRead):
    pass


def normalize_telegram_username(value: str | None) -> str | None:
    if value is None:
        return None
    username = value.strip()
    if username.startswith("@"):
        username = username[1:]
    if not TELEGRAM_USERNAME_RE.match(username):
        return None
    return username.lower()
