import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from app.modules.auth.telegram import TelegramInitDataError, validate_telegram_init_data

BOT_TOKEN = "123456:telegram-test-token"


def test_telegram_init_data_validation_accepts_signed_payload() -> None:
    now = datetime(2026, 5, 27, tzinfo=UTC)
    init_data = _build_init_data(
        {
            "auth_date": str(int(now.timestamp())),
            "user": json.dumps(
                {"id": 42, "username": "buyer", "first_name": "Ada"},
                separators=(",", ":"),
            ),
        }
    )

    payload = validate_telegram_init_data(
        init_data,
        BOT_TOKEN,
        max_age_seconds=60,
        now=now,
    )

    assert payload["auth_date"] == now
    assert payload["user"]["id"] == 42
    assert payload["user"]["username"] == "buyer"


def test_telegram_init_data_validation_rejects_bad_hash() -> None:
    now = datetime(2026, 5, 27, tzinfo=UTC)
    init_data = _build_init_data(
        {
            "auth_date": str(int(now.timestamp())),
            "user": json.dumps({"id": 42}, separators=(",", ":")),
        }
    )

    with pytest.raises(TelegramInitDataError, match="invalid"):
        validate_telegram_init_data(
            init_data.replace("hash=", "hash=bad"),
            BOT_TOKEN,
            now=now,
        )


def test_telegram_init_data_validation_rejects_expired_payload() -> None:
    now = datetime(2026, 5, 27, tzinfo=UTC)
    init_data = _build_init_data(
        {
            "auth_date": str(int((now - timedelta(seconds=61)).timestamp())),
            "user": json.dumps({"id": 42}, separators=(",", ":")),
        }
    )

    with pytest.raises(TelegramInitDataError, match="expired"):
        validate_telegram_init_data(
            init_data,
            BOT_TOKEN,
            max_age_seconds=60,
            now=now,
        )


def test_telegram_init_data_validation_rejects_future_payload() -> None:
    now = datetime(2026, 5, 27, tzinfo=UTC)
    init_data = _build_init_data(
        {
            "auth_date": str(int((now + timedelta(seconds=61)).timestamp())),
            "user": json.dumps({"id": 42}, separators=(",", ":")),
        }
    )

    with pytest.raises(TelegramInitDataError, match="future"):
        validate_telegram_init_data(
            init_data,
            BOT_TOKEN,
            max_age_seconds=60,
            now=now,
        )


def _build_init_data(values: dict[str, str]) -> str:
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    payload_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode({**values, "hash": payload_hash})
