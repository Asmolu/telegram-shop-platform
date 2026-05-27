from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl

MAX_AUTH_DATE_FUTURE_SECONDS = 60


class TelegramInitDataError(ValueError):
    pass


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise TelegramInitDataError("Telegram initData hash is missing")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramInitDataError("Telegram initData hash is invalid")

    auth_date_raw = parsed.get("auth_date")
    if auth_date_raw is None:
        raise TelegramInitDataError("Telegram initData auth_date is missing")

    try:
        auth_date = datetime.fromtimestamp(int(auth_date_raw), tz=UTC)
    except ValueError as exc:
        raise TelegramInitDataError("Telegram initData auth_date is invalid") from exc

    current_time = now or datetime.now(UTC)
    if (auth_date - current_time).total_seconds() > MAX_AUTH_DATE_FUTURE_SECONDS:
        raise TelegramInitDataError("Telegram initData auth_date is in the future")
    if max_age_seconds is not None and (current_time - auth_date).total_seconds() > max_age_seconds:
        raise TelegramInitDataError("Telegram initData is expired")

    payload: dict[str, Any] = dict(parsed)
    payload["auth_date"] = auth_date
    if "user" in payload:
        try:
            payload["user"] = json.loads(str(payload["user"]))
        except json.JSONDecodeError as exc:
            raise TelegramInitDataError("Telegram initData user payload is invalid") from exc

    return payload
