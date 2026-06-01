from app.core.config import settings

SELLER_BOT_WEBHOOK_PATH = "/telegram/seller-bot/webhook/"


def redact_sensitive_path(path: str) -> str:
    seller_webhook_prefix = (
        f"{settings.api_v1_prefix.rstrip('/')}{SELLER_BOT_WEBHOOK_PATH}"
    )
    if path.startswith(seller_webhook_prefix):
        return f"{seller_webhook_prefix}<secret>"
    return path
