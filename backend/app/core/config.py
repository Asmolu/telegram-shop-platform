from functools import cached_property
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PRODUCTION_ENVS = {"production", "prod", "staging"}
DEFAULT_JWT_SECRET_KEY = "change-me-in-local-env"
DEFAULT_UPLOADS_MOUNT_PATH = "/uploads"


def normalize_public_url(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        msg = "Public URL settings must not be empty"
        raise ValueError(msg)
    return stripped.rstrip("/") or "/"


def join_public_url(base_url: str, path: str) -> str:
    base = normalize_public_url(base_url)
    suffix = path.strip().lstrip("/")
    if not suffix:
        return base
    if base == "/":
        return f"/{suffix}"
    return f"{base}/{suffix}"


def _configured_chat_id(*values: str | None) -> str | None:
    for value in values:
        if value is not None and value.strip():
            return value.strip()
    return None


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
    telegram_orders_chat_id: str | None = None
    telegram_seller_chat_id: str | None = None
    telegram_returns_chat_id: str | None = None
    telegram_backup_chat_id: str | None = None
    telegram_seller_bot_username: str | None = None
    telegram_seller_webhook_secret: str | None = None
    telegram_customer_bot_token: str | None = None
    telegram_customer_bot_username: str | None = None
    telegram_customer_webhook_secret: str | None = None
    telegram_mini_app_short_name: str = ""
    telegram_channel_entry_start_param: str = "channel_pin"

    jwt_secret_key: str = DEFAULT_JWT_SECRET_KEY
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    telegram_auth_max_age_seconds: int = 86_400
    seller_registration_expires_minutes: int = 30
    seller_verification_code_expires_minutes: int = 10

    uploads_dir: str = "uploads"
    public_uploads_url: str = "/uploads"
    public_api_base_url: str = "http://localhost:8000"
    public_mini_app_base_url: str = "http://localhost:5173"
    public_seller_panel_base_url: str = "http://localhost:5174"
    upload_subdirs: tuple[str, ...] = (
        "products",
        "banners",
        "reviews",
        "categories",
        "tags",
        "customer_campaigns",
        "channel_entry",
        "payment_receipts",
        "returns",
        "looks",
        "temp",
    )

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
    rate_limit_telemetry_requests: int = 60
    rate_limit_telemetry_window_seconds: int = 60
    rate_limit_customer_campaign_requests: int = 30
    rate_limit_customer_campaign_window_seconds: int = 60

    telemetry_enabled: bool = True
    telemetry_max_events_per_batch: int = 25
    telemetry_max_body_bytes: int = 65_536
    telemetry_success_sample_rate: float = 0.2
    telemetry_web_vital_sample_rate: float = 0.5
    telemetry_route_sample_rate: float = 0.25
    telemetry_network_sample_rate: float = 0.25
    telemetry_retention_days: int = 60
    telemetry_cleanup_batch_size: int = 500

    customer_campaign_batch_size: int = 20
    customer_campaign_max_attempts: int = 3
    customer_campaign_retry_base_seconds: int = 60
    customer_campaign_worker_enabled: bool = True
    customer_campaign_worker_poll_seconds: int = 5
    customer_campaign_sending_timeout_seconds: int = 300

    manual_payment_expiration_worker_enabled: bool = True
    manual_payment_expiration_poll_seconds: int = 60

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def telegram_orders_notification_chat_id(self) -> str | None:
        return _configured_chat_id(self.telegram_orders_chat_id, self.telegram_seller_chat_id)

    @property
    def telegram_returns_notification_chat_id(self) -> str | None:
        return _configured_chat_id(self.telegram_returns_chat_id, self.telegram_seller_chat_id)

    @property
    def telegram_backup_notification_chat_id(self) -> str | None:
        return _configured_chat_id(self.telegram_backup_chat_id, self.telegram_seller_chat_id)

    @field_validator(
        "public_uploads_url",
        "public_api_base_url",
        "public_mini_app_base_url",
        "public_seller_panel_base_url",
    )
    @classmethod
    def normalize_public_url_setting(cls, value: str) -> str:
        return normalize_public_url(value)

    @cached_property
    def uploads_dir_path(self) -> Path:
        uploads_path = Path(self.uploads_dir)
        if uploads_path.is_absolute():
            return uploads_path
        return BACKEND_DIR / uploads_path

    @property
    def public_uploads_mount_path(self) -> str:
        value = normalize_public_url(self.public_uploads_url)
        if value.startswith(("http://", "https://")):
            mount_path = urlsplit(value).path.rstrip("/")
        else:
            mount_path = value.rstrip("/")
        if not mount_path or mount_path == "/":
            return DEFAULT_UPLOADS_MOUNT_PATH
        return mount_path if mount_path.startswith("/") else f"/{mount_path}"

    def public_upload_url_for(self, path: str) -> str:
        value = path.strip()
        if value.startswith(("http://", "https://")):
            return value
        mount_path = self.public_uploads_mount_path
        if value == mount_path:
            value = ""
        elif value.startswith(f"{mount_path}/"):
            value = value.removeprefix(mount_path)
        return join_public_url(self.public_uploads_url, value)

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
