import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import JsonLogFormatter
from app.main import create_app
from app.modules.auth.service import AuthService
from app.modules.auth.telegram import TelegramInitDataError, validate_telegram_init_data

BOT_TOKEN = "123456:telegram-test-token"


class DummySession:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def refresh(self, _: object) -> None:
        return None

    async def flush(self) -> None:
        return None


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


def test_telegram_init_data_validation_classifies_missing_init_data() -> None:
    with pytest.raises(TelegramInitDataError) as error:
        validate_telegram_init_data("", BOT_TOKEN)

    assert error.value.error_code == "missing_init_data"
    assert error.value.has_init_data is False
    assert error.value.has_user_payload is None


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


def test_auth_login_returns_sanitized_error_for_missing_init_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "telegram_webapp_bot_token", None)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    with TestClient(create_app()) as client:
        response = client.post("/api/v1/auth/telegram/login", json={"init_data": ""})

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Telegram authentication data"}
    assert "init_data" not in json.dumps(response.json(), ensure_ascii=False)


def test_auth_login_returns_sanitized_error_for_invalid_init_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submitted_payload = "hash=bad-sensitive-hash"
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "telegram_webapp_bot_token", None)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/telegram/login",
            json={"init_data": submitted_payload},
        )

    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid Telegram authentication data"}
    assert submitted_payload not in serialized
    assert "bad-sensitive-hash" not in serialized


@pytest.mark.asyncio
async def test_auth_login_logs_sanitized_invalid_init_data(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submitted_payload = "hash=bad-sensitive-hash"
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_TOKEN)
    monkeypatch.setattr(settings, "telegram_webapp_bot_token", None)
    service = AuthService(DummySession())  # type: ignore[arg-type]

    with caplog.at_level(logging.WARNING, logger="app.modules.auth.service"):
        with pytest.raises(AppError):
            await service.login_with_telegram(submitted_payload, request_id="req-auth")

    record = next(
        item for item in caplog.records
        if item.message == "telegram auth login rejected"
    )
    assert record.error_code == "invalid_signature"
    assert record.has_init_data is True
    assert record.has_user_payload is False
    assert record.auth_date_age_seconds is None
    assert record.request_id == "req-auth"
    serialized_record = json.dumps(record.__dict__, default=str, ensure_ascii=False)
    formatted_record = JsonLogFormatter().format(record)
    assert submitted_payload not in serialized_record
    assert submitted_payload not in formatted_record
    assert "bad-sensitive-hash" not in serialized_record
    assert "bad-sensitive-hash" not in formatted_record
    assert BOT_TOKEN not in serialized_record
    assert BOT_TOKEN not in formatted_record
    assert '"error_code": "invalid_signature"' in formatted_record
    assert '"has_init_data": true' in formatted_record
    assert '"has_user_payload": false' in formatted_record
    assert '"request_id": "req-auth"' in formatted_record


def _build_init_data(values: dict[str, str]) -> str:
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    payload_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode({**values, "hash": payload_hash})
