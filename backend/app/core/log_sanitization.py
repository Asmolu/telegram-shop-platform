from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import settings

SELLER_BOT_WEBHOOK_PATH = "/telegram/seller-bot/webhook/"
TELEGRAM_BOT_API_TOKEN_RE = re.compile(r"/bot[^/\s]+/")


def redact_sensitive_path(path: str) -> str:
    seller_webhook_prefix = (
        f"{settings.api_v1_prefix.rstrip('/')}{SELLER_BOT_WEBHOOK_PATH}"
    )
    if path.startswith(seller_webhook_prefix):
        return f"{seller_webhook_prefix}<secret>"
    return path


def redact_sensitive_text(value: str) -> str:
    redacted = TELEGRAM_BOT_API_TOKEN_RE.sub("/bot<redacted>/", value)
    redacted = _redact_seller_webhook_path_in_text(redacted)
    for secret in _configured_secret_values():
        redacted = redacted.replace(secret, "<redacted>")
    return redacted


class SensitiveDataLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_log_value(record.msg)
        record.args = _redact_log_value(record.args)
        return True


def _redact_log_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, tuple):
        return tuple(_redact_log_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_log_value(item) for item in value]
    if isinstance(value, dict):
        return {
            _redact_log_value(key): _redact_log_value(item)
            for key, item in value.items()
        }
    return value


def _configured_secret_values() -> tuple[str, ...]:
    return tuple(
        value
        for value in (
            settings.telegram_bot_token,
            settings.telegram_webapp_bot_token,
            settings.telegram_seller_webhook_secret,
        )
        if value
    )


def _redact_seller_webhook_path_in_text(value: str) -> str:
    seller_webhook_prefix = (
        f"{settings.api_v1_prefix.rstrip('/')}{SELLER_BOT_WEBHOOK_PATH}"
    )
    pattern = re.compile(rf"({re.escape(seller_webhook_prefix)})[^\s\"'?]+")
    return pattern.sub(r"\1<secret>", value)
