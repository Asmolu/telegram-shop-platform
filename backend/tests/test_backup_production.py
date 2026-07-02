from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

import scripts.backup_production as backup_module
from scripts.backup_production import (
    BACKUP_LOCK_FILENAME,
    BackupConfig,
    BackupError,
    BackupObject,
    BackupRunResult,
    YandexDiskClient,
    YandexDiskError,
    backup_run_lock,
    build_notification_message,
    build_yandex_remote_path,
    create_backup_metadata,
    generate_backup_id,
    sanitize_text,
    select_retention_deletes,
    upload_backup_archive,
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
            "refresh-token-secret-value from https://uploader.example/signed?token=secret "
            "using backend/.env.production credentials"
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
    assert "https://" not in message
    assert ".env.production" not in message
    assert "<redacted>" in message
    assert "Этап ошибки: yandex_upload" in message
    assert "❌ Ошибка резервного копирования" in message


def test_successful_telegram_notification_is_russian() -> None:
    result = BackupRunResult(
        backup_id="telegram-shop-prod-20260615-060011",
        environment="production",
        status="success",
        restore_verification_status="passed",
        remote_path="/TelegramShopPlatform/storage/backup.tar.gz",
        archive_size=108_527_616,
        local_retention_result="deleted 1 local archive(s)",
        remote_retention_result="deleted 1 remote archive(s)",
    )

    message = build_notification_message(result)

    assert "✅ Резервная копия Telegram Shop Platform создана" in message
    assert "Статус: успешно" in message
    assert "Проверка восстановления: пройдена" in message
    assert "Размер архива: 103.5 MiB" in message
    assert "Локальная очистка: удалено 1 архив(ов)" in message
    assert "Удалённая очистка: удалено 1 архив(ов)" in message


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


def test_backup_config_prefers_backup_chat_id() -> None:
    config = BackupConfig.from_mapping(
        {
            "TELEGRAM_BOT_TOKEN": "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
            "TELEGRAM_BACKUP_CHAT_ID": "-100-backup",
            "TELEGRAM_SELLER_CHAT_ID": "-100-legacy",
        }
    )

    assert config.telegram_notification_chat_id == "-100-backup"


def test_backup_config_falls_back_to_legacy_seller_chat_id() -> None:
    config = BackupConfig.from_mapping(
        {
            "TELEGRAM_BOT_TOKEN": "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
            "TELEGRAM_SELLER_CHAT_ID": "-100-legacy",
        }
    )

    assert config.telegram_notification_chat_id == "-100-legacy"


def test_backup_config_validation_mentions_backup_chat_id_when_chat_missing() -> None:
    config = BackupConfig.from_mapping(
        {
            "TELEGRAM_BOT_TOKEN": "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
        }
    )

    errors, _warnings = config.validate(require_yandex=False)

    assert any("TELEGRAM_BACKUP_CHAT_ID" in error for error in errors)


def test_backup_notify_uses_backup_chat_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, str]] = []

    class FakeTelegramNotifier:
        def __init__(self, *, bot_token: str, chat_id: str) -> None:
            sent.append((bot_token, chat_id))

        def send(self, message: str) -> None:
            sent.append(("message", message))

    config = replace(
        make_backup_config(tmp_path),
        telegram_notifications_enabled=True,
        telegram_bot_token="token",
        telegram_backup_chat_id="-100-backup",
        telegram_seller_chat_id="-100-legacy",
    )
    result = BackupRunResult(
        backup_id="telegram-shop-prod-20260615-060011",
        environment="production",
        status="success",
        restore_verification_status="passed",
        remote_path="/TelegramShopPlatform/storage/backup.tar.gz",
        archive_size=108_527_616,
    )
    monkeypatch.setattr(backup_module, "TelegramNotifier", FakeTelegramNotifier)

    backup_module.notify(config, result)

    assert sent[0] == ("token", "-100-backup")
    assert sent[1][0] == "message"


def test_sanitize_text_redacts_extra_secrets() -> None:
    message = sanitize_text(
        "failure includes secret-value and OAuth abcdefghijklmnopqrstuvwxyz123456",
        ["secret-value"],
    )

    assert "secret-value" not in message
    assert "OAuth abcdefghijklmnopqrstuvwxyz123456" not in message


@pytest.mark.skipif(backup_module.fcntl is None, reason="fcntl locking requires Linux")
def test_second_backup_run_exits_before_mutating_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_backup_config(tmp_path)
    config.local_dir.mkdir(parents=True)
    args = argparse.Namespace(
        env_file=config.env_file,
        compose_file=config.compose_file,
        skip_remote_upload=False,
    )
    called: list[str] = []

    monkeypatch.setattr(backup_module, "load_env_file", lambda _: {})
    monkeypatch.setattr(
        backup_module.BackupConfig,
        "from_mapping",
        lambda *args, **kwargs: config,
    )
    monkeypatch.setattr(backup_module, "dump_postgres", lambda *args: called.append("dump"))
    monkeypatch.setattr(backup_module, "archive_uploads", lambda *args: called.append("archive"))
    monkeypatch.setattr(
        backup_module,
        "upload_backup_archive",
        lambda *args: called.append("upload"),
    )
    monkeypatch.setattr(
        backup_module,
        "cleanup_local_retention",
        lambda *args: called.append("local_retention"),
    )
    monkeypatch.setattr(
        backup_module,
        "cleanup_remote_retention",
        lambda *args: called.append("remote_retention"),
    )

    lock_path = config.local_dir / BACKUP_LOCK_FILENAME
    with backup_run_lock(lock_path):
        exit_code = backup_module.run_backup(args)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert called == []
    assert "Another backup run is already in progress" in captured.err
    assert "failed_step: single_instance_lock" in captured.err


@pytest.mark.skipif(backup_module.fcntl is None, reason="fcntl locking requires Linux")
def test_backup_lock_releases_after_exception(tmp_path: Path) -> None:
    lock_path = tmp_path / BACKUP_LOCK_FILENAME

    with pytest.raises(RuntimeError, match="boom"):
        with backup_run_lock(lock_path):
            raise RuntimeError("boom")

    with backup_run_lock(lock_path):
        pass


@pytest.mark.skipif(backup_module.fcntl is None, reason="fcntl locking requires Linux")
def test_backup_lock_releases_after_keyboard_interrupt(tmp_path: Path) -> None:
    lock_path = tmp_path / BACKUP_LOCK_FILENAME

    with pytest.raises(KeyboardInterrupt):
        with backup_run_lock(lock_path):
            raise KeyboardInterrupt

    with backup_run_lock(lock_path):
        pass


def test_yandex_upload_retry_uses_fresh_stream_and_exact_content_length(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "backup.tar.gz"
    archive_bytes = b"complete-backup-archive"
    archive_path.write_bytes(archive_bytes)
    http_client = RecordingUploadClient(expected_size=len(archive_bytes))
    client = YandexDiskClient(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        retries=2,
        client=http_client,
    )
    client._access_token = "access-token"
    monkeypatch.setattr("scripts.backup_production.time.sleep", lambda _: None)

    metadata = client.upload_file(
        archive_path,
        "/TelegramShopPlatform/storage/backup.tar.gz",
    )

    assert metadata["size"] == len(archive_bytes)
    assert http_client.upload_hrefs == 2
    assert http_client.upload_bodies == [archive_bytes, archive_bytes]
    assert http_client.declared_lengths == [len(archive_bytes), len(archive_bytes)]
    assert http_client.upload_streams[0] is not http_client.upload_streams[1]
    assert http_client.upload_authorizations == [None, None]


def test_yandex_timeout_uses_bounded_timeout_and_skips_retention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = make_backup_config(tmp_path)
    http_client = TimeoutUploadClient(remote_size=None)
    yandex_client = YandexDiskClient(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        retries=3,
        client=http_client,
    )
    yandex_client._access_token = "access-token"
    results: list[BackupRunResult] = []

    prepare_successful_local_backup(monkeypatch)
    monkeypatch.setattr(backup_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(backup_module, "YandexDiskClient", lambda **kwargs: yandex_client)
    monkeypatch.setattr(backup_module, "notify", lambda config, result: results.append(result))
    monkeypatch.setattr(
        backup_module,
        "cleanup_remote_retention",
        lambda *args: pytest.fail("remote retention ran after failed upload"),
    )
    monkeypatch.setattr(
        backup_module,
        "cleanup_local_retention",
        lambda *args: pytest.fail("local retention ran after failed upload"),
    )

    exit_code = backup_module._run_backup_locked(
        argparse.Namespace(skip_remote_upload=False),
        {},
        config,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert results[-1].failed_step == "yandex_upload"
    assert results[-1].local_retention_result == "not_run"
    assert results[-1].remote_retention_result == "not_run"
    assert "timed out" in captured.err
    assert "Этап ошибки: yandex_upload" in captured.err
    assert http_client.upload_attempts == 3
    assert all(timeout.connect == 20.0 for timeout in http_client.timeouts)
    assert all(timeout.read == 120.0 for timeout in http_client.timeouts)
    assert all(timeout.write == 300.0 for timeout in http_client.timeouts)
    assert all(timeout.pool == 20.0 for timeout in http_client.timeouts)

    archives = list(config.local_dir.glob("*.tar.gz"))
    assert len(archives) == 1
    assert archives[0].read_bytes() == b"verified-final-archive"


def test_timed_out_upload_is_success_when_remote_size_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = b"complete-backup-archive"
    archive_path = tmp_path / "backup.tar.gz"
    archive_path.write_bytes(archive_bytes)
    http_client = TimeoutUploadClient(remote_size=len(archive_bytes))
    client = YandexDiskClient(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        retries=3,
        client=http_client,
    )
    client._access_token = "access-token"
    monkeypatch.setattr(backup_module.time, "sleep", lambda _: None)

    metadata = client.upload_file(archive_path, "/remote/backup.tar.gz")

    assert metadata["size"] == len(archive_bytes)
    assert http_client.upload_attempts == 1
    assert http_client.upload_hrefs == 1


def test_timed_out_upload_with_mismatched_remote_size_is_not_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_bytes = b"complete-backup-archive"
    archive_path = tmp_path / "backup.tar.gz"
    archive_path.write_bytes(archive_bytes)
    http_client = TimeoutUploadClient(remote_size=len(archive_bytes) - 1)
    client = YandexDiskClient(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        retries=2,
        client=http_client,
    )
    client._access_token = "access-token"
    monkeypatch.setattr(backup_module.time, "sleep", lambda _: None)

    with pytest.raises(YandexDiskError, match="timed out"):
        client.upload_file(archive_path, "/remote/backup.tar.gz")

    assert http_client.upload_attempts == 2
    assert http_client.upload_hrefs == 2


def test_yandex_auth_failure_is_not_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = tmp_path / "backup.tar.gz"
    archive_path.write_bytes(b"complete-backup-archive")
    http_client = AuthRejectedUploadClient()
    client = YandexDiskClient(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        retries=3,
        client=http_client,
    )
    client._access_token = "access-token"
    monkeypatch.setattr(backup_module.time, "sleep", lambda _: None)

    with pytest.raises(YandexDiskError, match=r"after 1 attempt\(s\).+HTTP 401"):
        client.upload_file(archive_path, "/remote/backup.tar.gz")

    assert http_client.upload_url_requests == 1


def test_keyboard_interrupt_exits_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupt(_: argparse.Namespace) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(backup_module, "run_backup", interrupt)

    exit_code = backup_module.main(["run"])

    captured = capsys.readouterr()
    assert exit_code == 130
    assert captured.err.strip() == "Backup interrupted by operator"
    assert "Traceback" not in captured.err


def test_upload_backup_archive_reports_precise_sanitized_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "refresh-token-secret-value"
    monkeypatch.setenv("YANDEX_REFRESH_TOKEN", secret)
    archive_path = tmp_path / "backup.tar.gz"
    archive_path.write_bytes(b"backup")

    class FailingClient:
        def upload_file(self, _: Path, __: str) -> dict[str, Any]:
            raise YandexDiskError(
                f"Too little data for declared Content-Length with {secret}"
            )

    with pytest.raises(BackupError) as error:
        upload_backup_archive(FailingClient(), archive_path, "/remote/backup.tar.gz")

    assert error.value.step == "yandex_upload"
    assert "Content-Length" in str(error.value)
    assert "unexpected" not in str(error.value)
    assert secret not in str(error.value)
    assert "<redacted>" in str(error.value)


class RecordingUploadClient:
    def __init__(self, *, expected_size: int) -> None:
        self.expected_size = expected_size
        self.upload_hrefs = 0
        self.upload_bodies: list[bytes] = []
        self.declared_lengths: list[int] = []
        self.upload_streams: list[Any] = []
        self.upload_authorizations: list[str | None] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Any = None,
        content: Any = None,
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Response:
        del data, timeout
        request = httpx.Request(method, url)
        if "/resources/upload?" in url:
            self.upload_hrefs += 1
            return httpx.Response(
                200,
                json={"href": f"https://upload.example/{self.upload_hrefs}"},
                request=request,
            )
        if url.startswith("https://upload.example/"):
            assert content is not None
            self.upload_streams.append(content)
            body = b"".join(content)
            self.upload_bodies.append(body)
            self.declared_lengths.append(int((headers or {})["Content-Length"]))
            self.upload_authorizations.append((headers or {}).get("Authorization"))
            if len(self.upload_bodies) == 1:
                raise httpx.WriteError(
                    "Too little data for declared Content-Length",
                    request=request,
                )
            return httpx.Response(201, request=request)
        if method == "GET" and "/resources?" in url:
            if len(self.upload_bodies) == 1:
                return httpx.Response(404, request=request)
            return httpx.Response(
                200,
                json={"size": self.expected_size},
                request=request,
            )
        if method == "PUT" and "/resources?" in url:
            return httpx.Response(201, request=request)
        raise AssertionError(f"Unexpected request: {method} {url}")


class TimeoutUploadClient:
    def __init__(self, *, remote_size: int | None) -> None:
        self.remote_size = remote_size
        self.upload_hrefs = 0
        self.upload_attempts = 0
        self.timeouts: list[httpx.Timeout] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Any = None,
        content: Any = None,
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Response:
        del data, headers
        assert timeout is not None
        self.timeouts.append(timeout)
        request = httpx.Request(method, url)
        if "/resources/upload?" in url:
            self.upload_hrefs += 1
            return httpx.Response(
                200,
                json={"href": f"https://upload.example/{self.upload_hrefs}"},
                request=request,
            )
        if url.startswith("https://upload.example/"):
            assert content is not None
            assert b"".join(content)
            self.upload_attempts += 1
            raise httpx.ReadTimeout("response headers timed out", request=request)
        if method == "GET" and "/resources?" in url:
            if self.remote_size is None:
                return httpx.Response(404, request=request)
            return httpx.Response(200, json={"size": self.remote_size}, request=request)
        if method == "PUT" and "/resources?" in url:
            return httpx.Response(201, request=request)
        raise AssertionError(f"Unexpected request: {method} {url}")


class AuthRejectedUploadClient:
    def __init__(self) -> None:
        self.upload_url_requests = 0

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Any = None,
        content: Any = None,
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> httpx.Response:
        del data, content, headers
        assert timeout is not None
        request = httpx.Request(method, url)
        if "/resources/upload?" in url:
            self.upload_url_requests += 1
            return httpx.Response(401, text="invalid OAuth token", request=request)
        if method == "PUT" and "/resources?" in url:
            return httpx.Response(201, request=request)
        raise AssertionError(f"Unexpected request: {method} {url}")


def make_backup_config(tmp_path: Path) -> BackupConfig:
    env_file = tmp_path / "backup.env"
    compose_file = tmp_path / "compose.yml"
    env_file.write_text("BACKUP_ENABLED=true\n", encoding="utf-8")
    compose_file.write_text("services: {}\n", encoding="utf-8")
    return BackupConfig(
        backup_enabled=True,
        environment="production",
        local_dir=tmp_path / "backups",
        remote_dir="/TelegramShopPlatform/storage",
        interval_hours=6,
        retention_max_count=20,
        retention_days=5,
        restore_verify_enabled=True,
        telegram_notifications_enabled=False,
        telegram_bot_token=None,
        telegram_backup_chat_id=None,
        telegram_seller_chat_id=None,
        yandex_client_id="client-id",
        yandex_client_secret="client-secret",
        yandex_refresh_token="refresh-token",
        postgres_db="telegram_shop",
        postgres_user="telegram_shop",
        compose_file=compose_file,
        env_file=env_file,
    )


def prepare_successful_local_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backup_module,
        "dump_postgres",
        lambda config, path: path.write_bytes(b"postgres-dump"),
    )
    monkeypatch.setattr(
        backup_module,
        "archive_uploads",
        lambda config, path: path.write_bytes(b"uploads-archive"),
    )
    monkeypatch.setattr(
        backup_module,
        "restore_verify",
        lambda *args: {"status": "passed"},
    )
    monkeypatch.setattr(backup_module, "get_git_commit", lambda: None)
    monkeypatch.setattr(backup_module, "get_alembic_current", lambda config: None)
    monkeypatch.setattr(
        backup_module,
        "create_final_archive",
        lambda work_dir, archive_path: archive_path.write_bytes(b"verified-final-archive"),
    )
