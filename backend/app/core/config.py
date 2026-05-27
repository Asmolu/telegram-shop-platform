from functools import cached_property
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Telegram Shop Platform API"
    app_env: str = "local"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/telegram_shop"
    redis_url: str = "redis://redis:6379/0"

    telegram_bot_token: str | None = None
    telegram_webapp_bot_token: str | None = None
    telegram_seller_chat_id: str | None = None

    jwt_secret_key: str = "change-me-in-local-env"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    telegram_auth_max_age_seconds: int = 86_400

    uploads_dir: str = "uploads"
    public_uploads_url: str = "/uploads"
    upload_subdirs: tuple[str, ...] = ("products", "banners", "reviews", "temp")

    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost:5174,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @cached_property
    def uploads_dir_path(self) -> Path:
        uploads_path = Path(self.uploads_dir)
        if uploads_path.is_absolute():
            return uploads_path
        return BACKEND_DIR / uploads_path


settings = Settings()
