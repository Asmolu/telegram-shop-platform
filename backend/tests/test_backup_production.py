from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scripts.backup_production import (
    BackupConfig,
    BackupObject,
    BackupRunResult,
    build_notification_message,
    build_yandex_remote_path,
    create_backup_metadata,
    generate_backup_id,
    sanitize_text,
    select_retention_deletes,
)


def test_generate_backup_id_uses_production_short_name() -> None:
    created_at = datetime(2026, 6, 5, 12, 34, 56, tzinfo=UTC)

    assert generate_backup_id(created_at, "production") == "telegram-shop-prod-20260605-123456"


def test_yandex_remote_path_construction_normalizes_slashes() -> None:
    path = build_yandex_remote_path(
        "/TelegramShopPlatform/storage/",
        "telegram-shop-prod-20260605-123456.tar.gz",
    )

    assert path == "/TelegramShopPlatform/storage/telegram-shop-prod-20260605-123456.tar.gz"


def test_retention_selection_deletes_old_and_count_excess_without_current() -> None:
    now = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    backups = [
        BackupObject(
            name=f"telegram-shop-prod-202606{i + 1:02d}-000000.tar.gz",
            path=f"/remote/{i}",
            created_at=now - timedelta(hours=i),
            size=100,
        )
        for i in range(22)
    ]
    old_backup = BackupObject(
        name="telegram-shop-prod-20260520-000000.tar.gz",
        path="/remote/old",
        created_at=now - timedelta(days=16),
        size=100,
    )
    current_name = backups[-1].name

    deletes = select_retention_deletes(
        [*backups, old_backup],
        current_name=current_name,
        now=now,
        max_count=20,
        retention_days=5,
    )
    delete_names = {backup.name for backup in deletes}

    assert current_name not in delete_names
    assert old_backup.name in delete_names
    assert len([name for name in delete_names if name != old_backup.name]) == 2


def test_metadata_creation_does_not_store_secret_values() -> None:
    metadata = create_backup_metadata(
        backup_id="telegram-shop-prod-20260605-123456",
        created_at=datetime(2026, 6, 5, 12, 34, 56, tzinfo=UTC),
        environment="production",
        git_commit="abc123",
        alembic_current="20260605_0018",
        compose_file=BackupConfig.from_mapping({}).compose_file,
        restore_status="passed",
        remote_path="/TelegramShopPlatform/storage/telegram-shop-prod-20260605-123456.tar.gz",
    )
    rendered = str(metadata)

    assert metadata["backup_id"] == "telegram-shop-prod-20260605-123456"
    assert metadata["restore_verification"]["status"] == "passed"
    assert "postgres.dump" in rendered
    assert ".env.production contents" in rendered
    assert "super-secret-password" not in rendered
    assert "YANDEX_REFRESH_TOKEN" not in rendered


def test_telegram_notification_sanitizes_known_secret_env_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:abcdefghijklmnopqrstuvwxyzABCDE")
    monkeypatch.setenv("YANDEX_REFRESH_TOKEN", "refresh-token-secret-value")
    result = BackupRunResult(
        backup_id="telegram-shop-prod-20260605-123456",
        environment="production",
        status="failed",
        failed_step="yandex_upload",
        error=(
            "upload failed with 123456789:abcdefghijklmnopqrstuvwxyzABCDE and "
            "refresh-token-secret-value"
        ),
        restore_verification_status="passed",
        remote_path="/TelegramShopPlatform/storage/telegram-shop-prod-20260605-123456.tar.gz",
        archive_size=2048,
        local_retention_result="deleted 0 local archive(s)",
        remote_retention_result="not_run",
    )

    message = build_notification_message(result)

    assert "123456789:abcdefghijklmnopqrstuvwxyzABCDE" not in message
    assert "refresh-token-secret-value" not in message
    assert "<redacted>" in message
    assert "failed_step: yandex_upload" in message


def test_config_validation_requires_restore_verification_and_policy_values() -> None:
    config = BackupConfig.from_mapping(
        {
            "BACKUP_RESTORE_VERIFY_ENABLED": "false",
            "BACKUP_INTERVAL_HOURS": "12",
            "BACKUP_RETENTION_MAX_COUNT": "30",
            "BACKUP_RETENTION_DAYS": "10",
            "TELEGRAM_BOT_TOKEN": "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
            "TELEGRAM_SELLER_CHAT_ID": "-1001234567890",
            "YANDEX_CLIENT_ID": "client-id",
            "YANDEX_CLIENT_SECRET": "client-secret",
            "YANDEX_REFRESH_TOKEN": "refresh-token",
        }
    )

    errors, _warnings = config.validate(require_yandex=True)

    assert any("BACKUP_RESTORE_VERIFY_ENABLED" in error for error in errors)
    assert any("BACKUP_INTERVAL_HOURS" in error for error in errors)
    assert any("BACKUP_RETENTION_MAX_COUNT" in error for error in errors)
    assert any("BACKUP_RETENTION_DAYS" in error for error in errors)


def test_config_validation_reports_missing_yandex_credentials() -> None:
    config = BackupConfig.from_mapping(
        {
            "TELEGRAM_BOT_TOKEN": "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
            "TELEGRAM_SELLER_CHAT_ID": "-1001234567890",
        }
    )

    errors, _warnings = config.validate(require_yandex=True)

    assert any("YANDEX_CLIENT_ID" in error for error in errors)


def test_sanitize_text_redacts_extra_secrets() -> None:
    message = sanitize_text(
        "failure includes secret-value and OAuth abcdefghijklmnopqrstuvwxyz123456",
        ["secret-value"],
    )

    assert "secret-value" not in message
    assert "OAuth abcdefghijklmnopqrstuvwxyz123456" not in message
