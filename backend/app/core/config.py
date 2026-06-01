from functools import cached_property
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PRODUCTION_ENVS = {"production", "prod", "staging"}
DEFAULT_JWT_SECRET_KEY = "change-me-in-local-env"


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
    telegram_seller_bot_username: str | None = None
    telegram_seller_webhook_secret: str | None = None

    jwt_secret_key: str = DEFAULT_JWT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    telegram_auth_max_age_seconds: int = 86_400
    seller_registration_expires_minutes: int = 30
    seller_verification_code_expires_minutes: int = 10

    uploads_dir: str = "uploads"
    public_uploads_url: str = "/uploads"
    upload_subdirs: tuple[str, ...] = ("products", "banners", "reviews", "temp")

    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost:5174,http://localhost:3000",
        alias="CORS_ORIGINS",
    )

    log_level: str = "INFO"
    log_format: str = "json"

    error_monitoring_enabled: bool = False
    sentry_dsn: str | None = None

    cache_enabled: bool = True
    cache_public_products_ttl_seconds: int = 60
    cache_public_product_detail_ttl_seconds: int = 60
    cache_taxonomy_ttl_seconds: int = 300
    cache_banners_ttl_seconds: int = 60
    cache_reviews_ttl_seconds: int = 120

    rate_limit_enabled: bool = True
    rate_limit_redis_enabled: bool = True
    rate_limit_in_memory_fallback_enabled: bool = True
    rate_limit_global_requests: int = 600
    rate_limit_global_window_seconds: int = 60
    rate_limit_auth_requests: int = 10
    rate_limit_auth_window_seconds: int = 60
    rate_limit_upload_requests: int = 30
    rate_limit_upload_window_seconds: int = 60
    rate_limit_checkout_requests: int = 10
    rate_limit_checkout_window_seconds: int = 60
    rate_limit_promo_requests: int = 30
    rate_limit_promo_window_seconds: int = 60
    rate_limit_review_requests: int = 10
    rate_limit_review_window_seconds: int = 60

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @cached_property
    def uploads_dir_path(self) -> Path:
        uploads_path = Path(self.uploads_dir)
        if uploads_path.is_absolute():
            return uploads_path
        return BACKEND_DIR / uploads_path

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.app_env.lower() not in PRODUCTION_ENVS:
            return self

        if self.jwt_secret_key == DEFAULT_JWT_SECRET_KEY:
            msg = "JWT_SECRET_KEY must be changed for production or staging environments"
            raise ValueError(msg)
        if "*" in self.cors_origins:
            msg = "CORS_ORIGINS must not contain '*' in production or staging environments"
            raise ValueError(msg)
        return self


settings = Settings()
