import pytest

from app.core.config import Settings


def test_settings_load_split_telegram_chat_env(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_ORDERS_CHAT_ID", "-100-orders")
    monkeypatch.setenv("TELEGRAM_RETURNS_CHAT_ID", "-100-returns")
    monkeypatch.setenv("TELEGRAM_BACKUP_CHAT_ID", "-100-backup")
    monkeypatch.setenv("TELEGRAM_SELLER_CHAT_ID", "-100-legacy")

    config = Settings(_env_file=None, app_env="local")

    assert config.telegram_orders_chat_id == "-100-orders"
    assert config.telegram_returns_chat_id == "-100-returns"
    assert config.telegram_backup_chat_id == "-100-backup"
    assert config.telegram_orders_notification_chat_id == "-100-orders"
    assert config.telegram_returns_notification_chat_id == "-100-returns"
    assert config.telegram_backup_notification_chat_id == "-100-backup"


def test_settings_split_telegram_chat_fallbacks() -> None:
    config = Settings(
        _env_file=None,
        app_env="local",
        telegram_orders_chat_id=None,
        telegram_returns_chat_id=None,
        telegram_backup_chat_id=None,
        telegram_seller_chat_id="-100-legacy",
    )

    assert config.telegram_orders_notification_chat_id == "-100-legacy"
    assert config.telegram_returns_notification_chat_id == "-100-legacy"
    assert config.telegram_backup_notification_chat_id == "-100-legacy"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outbox_poll_interval_seconds", 0),
        ("outbox_batch_size", 0),
        ("outbox_max_attempts", 0),
        ("outbox_lock_timeout_seconds", 0),
        ("outbox_retry_base_seconds", 0),
    ],
)
def test_outbox_settings_must_be_positive(field: str, value: int) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})


def test_outbox_retry_maximum_cannot_be_below_base() -> None:
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            outbox_retry_base_seconds=10,
            outbox_retry_max_seconds=9,
        )
