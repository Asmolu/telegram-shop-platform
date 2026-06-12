from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
DEFAULT_ENV_FILE = BACKEND_DIR / ".env.production"
DEFAULT_COMPOSE_FILE = ROOT_DIR / "docker-compose.prod.yml"

BACKUP_ID_RE = re.compile(r"^telegram-shop-[a-z0-9-]+-(?P<stamp>\d{8}-\d{6})$")
ARCHIVE_RE = re.compile(r"^telegram-shop-[a-z0-9-]+-(?P<stamp>\d{8}-\d{6})\.tar\.gz$")
SAFE_ENV_RE = re.compile(r"[^a-z0-9-]+")
RESTORE_DB_RE = re.compile(r"^telegram_shop_restore_check_[a-z0-9_]+$")
TELEGRAM_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
BEARER_TOKEN_RE = re.compile(r"\b(?:OAuth|Bearer)\s+[A-Za-z0-9._~+/=-]{12,}\b", re.I)
LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
SECRET_KEY_HINTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PRIVATE",
    "WEBHOOK",
    "DATABASE_URL",
    "YANDEX",
    "SENTRY_DSN",
    "JWT",
)
TRANSIENT_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
CHECKSUM_FILENAMES = ("postgres.dump", "uploads.tar.gz", "backup_metadata.json")
KEY_TABLES = (
    "alembic_version",
    "users",
    "categories",
    "products",
    "product_variants",
    "orders",
    "order_items",
    "product_images",
    "coupon_usages",
    "audit_logs",
)
UPLOADS_STREAM_CODE = """
import pathlib
import sys
import tarfile

root = pathlib.Path("/app/uploads")
with tarfile.open(fileobj=sys.stdout.buffer, mode="w:gz") as archive:
    if root.exists():
        for child in sorted(root.rglob("*")):
            archive.add(child, arcname=child.relative_to(root))
""".strip()


class BackupError(Exception):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(message)
        self.step = step


class YandexDiskError(Exception):
    pass


@dataclass(frozen=True)
class BackupConfig:
    backup_enabled: bool
    environment: str
    local_dir: Path
    remote_dir: str
    interval_hours: int
    retention_max_count: int
    retention_days: int
    restore_verify_enabled: bool
    telegram_notifications_enabled: bool
    telegram_bot_token: str | None
    telegram_seller_chat_id: str | None
    yandex_client_id: str | None
    yandex_client_secret: str | None
    yandex_refresh_token: str | None
    postgres_db: str
    postgres_user: str
    compose_file: Path
    env_file: Path

    @classmethod
    def from_mapping(
        cls,
        values: dict[str, str],
        *,
        env_file: Path = DEFAULT_ENV_FILE,
        compose_file: Path = DEFAULT_COMPOSE_FILE,
    ) -> BackupConfig:
        local_dir_raw = values.get("BACKUP_LOCAL_DIR", "backups")
        local_dir = Path(local_dir_raw)
        if not local_dir.is_absolute():
            local_dir = ROOT_DIR / local_dir

        return cls(
            backup_enabled=parse_bool(values.get("BACKUP_ENABLED", "true")),
            environment=values.get("BACKUP_ENVIRONMENT", values.get("APP_ENV", "production")),
            local_dir=local_dir,
            remote_dir=values.get("BACKUP_REMOTE_DIR", "/TelegramShopPlatform/storage"),
            interval_hours=parse_int(values.get("BACKUP_INTERVAL_HOURS"), 6),
            retention_max_count=parse_int(values.get("BACKUP_RETENTION_MAX_COUNT"), 20),
            retention_days=parse_int(values.get("BACKUP_RETENTION_DAYS"), 5),
            restore_verify_enabled=parse_bool(
                values.get("BACKUP_RESTORE_VERIFY_ENABLED", "true")
            ),
            telegram_notifications_enabled=parse_bool(
                values.get("BACKUP_TELEGRAM_NOTIFICATIONS_ENABLED", "true")
            ),
            telegram_bot_token=blank_to_none(values.get("TELEGRAM_BOT_TOKEN")),
            telegram_seller_chat_id=blank_to_none(values.get("TELEGRAM_SELLER_CHAT_ID")),
            yandex_client_id=blank_to_none(values.get("YANDEX_CLIENT_ID")),
            yandex_client_secret=blank_to_none(values.get("YANDEX_CLIENT_SECRET")),
            yandex_refresh_token=blank_to_none(values.get("YANDEX_REFRESH_TOKEN")),
            postgres_db=values.get("POSTGRES_DB", "telegram_shop"),
            postgres_user=values.get("POSTGRES_USER", "telegram_shop"),
            compose_file=compose_file,
            env_file=env_file,
        )

    def validate(self, *, require_yandex: bool = True) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []

        if not self.environment.strip():
            errors.append("BACKUP_ENVIRONMENT must not be empty.")
        if self.interval_hours != 6:
            errors.append("BACKUP_INTERVAL_HOURS must be 6 for the MVP production policy.")
        if self.retention_max_count != 20:
            errors.append("BACKUP_RETENTION_MAX_COUNT must be 20 for the MVP policy.")
        if self.retention_days != 5:
            errors.append("BACKUP_RETENTION_DAYS must be 5 for the MVP policy.")
        if not self.restore_verify_enabled:
            errors.append("BACKUP_RESTORE_VERIFY_ENABLED must stay true for production backups.")
        if not self.postgres_db.strip():
            errors.append("POSTGRES_DB must not be empty.")
        if not self.postgres_user.strip():
            errors.append("POSTGRES_USER must not be empty.")
        if not self.compose_file.exists():
            errors.append(f"Compose file is missing: {self.compose_file}")
        if not self.env_file.exists():
            warnings.append(f"Environment file is missing: {self.env_file}")
        if self.telegram_notifications_enabled and (
            not self.telegram_bot_token or not self.telegram_seller_chat_id
        ):
            errors.append(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_SELLER_CHAT_ID are required for backup "
                "notifications when BACKUP_TELEGRAM_NOTIFICATIONS_ENABLED=true."
            )

        yandex_missing = [
            name
            for name, value in (
                ("YANDEX_CLIENT_ID", self.yandex_client_id),
                ("YANDEX_CLIENT_SECRET", self.yandex_client_secret),
                ("YANDEX_REFRESH_TOKEN", self.yandex_refresh_token),
            )
            if not value
        ]
        if yandex_missing and require_yandex:
            errors.append(
                "Yandex Disk upload requires these variables: " + ", ".join(yandex_missing)
            )
        elif yandex_missing:
            warnings.append(
                "Yandex Disk upload would be skipped because these variables are missing: "
                + ", ".join(yandex_missing)
            )

        return errors, warnings


@dataclass(frozen=True)
class BackupObject:
    name: str
    path: str
    created_at: datetime
    size: int


@dataclass
class BackupRunResult:
    backup_id: str
    environment: str
    status: str = "running"
    failed_step: str | None = None
    error: str | None = None
    restore_verification_status: str = "pending"
    remote_path: str | None = None
    archive_size: int = 0
    local_retention_result: str = "not_run"
    remote_retention_result: str = "not_run"


class YandexDiskClient:
    token_url = "https://oauth.yandex.com/token"
    api_base_url = "https://cloud-api.yandex.net/v1/disk"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        timeout_seconds: float = 60.0,
        retries: int = 3,
        client: httpx.Client | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self._access_token: str | None = None

    def refresh_access_token(self) -> str:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = self._request(
            "POST",
            self.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            expected_statuses={200},
            include_auth=False,
        )
        payload = response.json()
        access_token = str(payload.get("access_token") or "")
        if not access_token:
            raise YandexDiskError("Yandex OAuth response did not include access_token.")
        self._access_token = access_token
        return access_token

    def upload_file(self, local_path: Path, remote_path: str) -> dict[str, Any]:
        token = self._require_access_token()
        self.ensure_directory(remote_parent(remote_path))
        local_size = local_path.stat().st_size
        last_error: YandexDiskError | None = None

        for attempt in range(1, self.retries + 1):
            try:
                params = urlencode({"path": remote_path, "overwrite": "true"})
                upload_info = self._request_json(
                    "GET",
                    f"{self.api_base_url}/resources/upload?{params}",
                    token=token,
                    expected_statuses={200},
                )
                href = str(upload_info.get("href") or "")
                if not href:
                    raise YandexDiskError("Yandex Disk did not return an upload href.")

                with local_path.open("rb") as file_obj:
                    self._request(
                        "PUT",
                        href,
                        content=file_obj,
                        headers={
                            "Authorization": f"OAuth {token}",
                            "Content-Length": str(local_size),
                            "Content-Type": "application/gzip",
                        },
                        expected_statuses={201, 202},
                        include_auth=False,
                        max_attempts=1,
                    )

                if local_path.stat().st_size != local_size:
                    raise YandexDiskError("Local backup archive changed during upload.")

                metadata = self.get_metadata(remote_path)
                remote_size = int(metadata.get("size") or 0)
                if remote_size != local_size:
                    raise YandexDiskError(
                        "Yandex Disk size verification failed: "
                        f"local={local_size} remote={remote_size}"
                    )
                return metadata
            except YandexDiskError as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(attempt * 2, 5))
                    continue

        detail = sanitize_text(str(last_error), configured_secret_values())
        raise YandexDiskError(
            f"Yandex Disk upload failed after {self.retries} attempt(s): {detail}"
        ) from last_error

    def ensure_directory(self, remote_dir: str) -> None:
        token = self._require_access_token()
        current = ""
        for part in remote_dir.strip("/").split("/"):
            if not part:
                continue
            current = f"{current}/{part}"
            params = urlencode({"path": current})
            self._request(
                "PUT",
                f"{self.api_base_url}/resources?{params}",
                headers={"Authorization": f"OAuth {token}"},
                expected_statuses={201, 409},
                include_auth=False,
            )

    def list_backups(self, remote_dir: str) -> list[BackupObject]:
        token = self._require_access_token()
        params = urlencode(
            {
                "path": normalize_remote_dir(remote_dir),
                "limit": "1000",
                "fields": "_embedded.items.name,_embedded.items.path,"
                "_embedded.items.modified,_embedded.items.created,_embedded.items.size",
            }
        )
        payload = self._request_json(
            "GET",
            f"{self.api_base_url}/resources?{params}",
            token=token,
            expected_statuses={200},
        )
        items = payload.get("_embedded", {}).get("items", [])
        backups: list[BackupObject] = []
        for item in items:
            name = str(item.get("name") or "")
            if not ARCHIVE_RE.match(name):
                continue
            created = parse_remote_datetime(item.get("modified") or item.get("created"))
            backups.append(
                BackupObject(
                    name=name,
                    path=str(item.get("path") or build_yandex_remote_path(remote_dir, name)),
                    created_at=created,
                    size=int(item.get("size") or 0),
                )
            )
        return backups

    def delete(self, remote_path: str) -> None:
        token = self._require_access_token()
        params = urlencode({"path": remote_path, "permanently": "true"})
        self._request(
            "DELETE",
            f"{self.api_base_url}/resources?{params}",
            headers={"Authorization": f"OAuth {token}"},
            expected_statuses={202, 204},
            include_auth=False,
        )

    def get_metadata(self, remote_path: str) -> dict[str, Any]:
        token = self._require_access_token()
        params = urlencode({"path": remote_path, "fields": "name,path,size,created,modified"})
        return self._request_json(
            "GET",
            f"{self.api_base_url}/resources?{params}",
            token=token,
            expected_statuses={200},
        )

    def _require_access_token(self) -> str:
        return self._access_token or self.refresh_access_token()

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        token: str,
        expected_statuses: set[int],
    ) -> dict[str, Any]:
        response = self._request(
            method,
            url,
            headers={"Authorization": f"OAuth {token}"},
            expected_statuses=expected_statuses,
            include_auth=False,
        )
        if not response.content:
            return {}
        return response.json()

    def _request(
        self,
        method: str,
        url: str,
        *,
        expected_statuses: set[int],
        include_auth: bool,
        data: dict[str, str] | None = None,
        content: Any | None = None,
        headers: dict[str, str] | None = None,
        max_attempts: int | None = None,
    ) -> httpx.Response:
        request_headers = dict(headers or {})
        request_data: Any = data
        if data and request_headers.get("Content-Type") == "application/x-www-form-urlencoded":
            request_data = urlencode(data)

        last_error: Exception | None = None
        attempts = self.retries if max_attempts is None else max_attempts
        for attempt in range(1, attempts + 1):
            try:
                response = self.client.request(
                    method,
                    url,
                    data=request_data,
                    content=content,
                    headers=request_headers if include_auth or request_headers else None,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(min(attempt * 2, 5))
                    continue
                raise YandexDiskError(sanitize_text(str(exc), configured_secret_values())) from exc

            if response.status_code in expected_statuses:
                return response
            if response.status_code in TRANSIENT_HTTP_STATUSES and attempt < attempts:
                time.sleep(min(attempt * 2, 5))
                continue
            message = sanitize_text(response.text[:500], configured_secret_values())
            raise YandexDiskError(f"Yandex Disk API returned {response.status_code}: {message}")

        raise YandexDiskError(sanitize_text(str(last_error), configured_secret_values()))


class TelegramNotifier:
    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def send(self, message: str) -> None:
        safe_message = sanitize_text(message, configured_secret_values())
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        response = self.client.post(
            url,
            json={
                "chat_id": self.chat_id,
                "text": safe_message,
                "disable_web_page_preview": True,
            },
        )
        if response.status_code >= 400:
            raise BackupError(
                "telegram_notification",
                f"Telegram API returned {response.status_code}: "
                f"{sanitize_text(response.text[:300], configured_secret_values())}",
            )


def parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value: str | None, default: int) -> int:
    try:
        return int(str(value if value is not None else default).strip())
    except ValueError:
        return default


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def load_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value.startswith(("'", '"'))
            ):
                value = value[1:-1]
            values[key] = value
    values.update({key: value for key, value in os.environ.items()})
    return values


def generate_backup_id(created_at: datetime, environment: str) -> str:
    safe_environment = SAFE_ENV_RE.sub("-", environment.lower()).strip("-")
    if safe_environment in {"production", "prod"}:
        safe_environment = "prod"
    if not safe_environment:
        safe_environment = "unknown"
    return f"telegram-shop-{safe_environment}-{created_at.strftime('%Y%m%d-%H%M%S')}"


def build_yandex_remote_path(remote_dir: str, archive_name: str) -> str:
    return f"{normalize_remote_dir(remote_dir)}/{archive_name}"


def normalize_remote_dir(remote_dir: str) -> str:
    normalized = "/" + remote_dir.strip("/")
    return normalized.rstrip("/") or "/"


def remote_parent(remote_path: str) -> str:
    normalized = "/" + remote_path.strip("/")
    parent = normalized.rsplit("/", 1)[0]
    return parent or "/"


def configured_secret_values(env: dict[str, str] | None = None) -> list[str]:
    source = env or os.environ
    secrets: list[str] = []
    for key, value in source.items():
        if len(value) < 4:
            continue
        if any(hint in key.upper() for hint in SECRET_KEY_HINTS):
            secrets.append(value)
    return secrets


def sanitize_text(text: str, extra_secrets: Iterable[str] = ()) -> str:
    sanitized = str(text)
    for secret in extra_secrets:
        if secret:
            sanitized = sanitized.replace(secret, "<redacted>")
    sanitized = TELEGRAM_TOKEN_RE.sub("<redacted>", sanitized)
    sanitized = BEARER_TOKEN_RE.sub("<redacted>", sanitized)
    sanitized = LONG_SECRET_RE.sub(lambda match: _redact_long_secret(match.group(0)), sanitized)
    sanitized = sanitized.replace(str(DEFAULT_ENV_FILE), "backend/.env.production")
    return sanitized[:3500]


def _redact_long_secret(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", value, re.I):
        return value
    if re.fullmatch(r"[0-9a-f]{64}", value, re.I):
        return "<redacted>"
    return value


def create_backup_metadata(
    *,
    backup_id: str,
    created_at: datetime,
    environment: str,
    git_commit: str | None,
    alembic_current: str | None,
    compose_file: Path,
    restore_status: str,
    remote_path: str,
) -> dict[str, Any]:
    return {
        "backup_id": backup_id,
        "created_at_utc": format_utc(created_at),
        "environment": environment,
        "git_commit": git_commit or "unavailable",
        "alembic_current": alembic_current or "unavailable",
        "compose_file": compose_file.name,
        "postgres_dump": "postgres.dump",
        "uploads_archive": "uploads.tar.gz",
        "restore_verification": {
            "status": restore_status,
            "verified_at_utc": format_utc(datetime.now(UTC))
            if restore_status == "passed"
            else None,
        },
        "remote": {
            "provider": "yandex_disk",
            "path": remote_path,
        },
        "checksums": "checksums.sha256",
        "notes": (
            "No secrets, tokens, passwords, private keys, .env.production contents, "
            "or Redis data are stored in backup metadata. Redis is cache/rate-limit "
            "state and is not backed up."
        ),
    }


def format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_command(
    command: list[str],
    *,
    cwd: Path = ROOT_DIR,
    step: str,
    stdout: Any | None = None,
    stdin: Any | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        command,
        cwd=cwd,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=stdin,
        text=stdout is None and stdin is None,
        check=False,
    )
    if process.returncode != 0:
        stderr = process.stderr if isinstance(process.stderr, str) else str(process.stderr)
        raise BackupError(step, sanitize_text(stderr.strip() or f"{command[0]} failed"))
    return process


def compose_base_command(config: BackupConfig) -> list[str]:
    command = ["docker", "compose"]
    if config.env_file.exists():
        command.extend(["--env-file", str(config.env_file)])
    command.extend(["-f", str(config.compose_file)])
    return command


def dump_postgres(config: BackupConfig, dump_path: Path) -> None:
    command = compose_base_command(config) + [
        "exec",
        "-T",
        "postgres",
        "pg_dump",
        "-U",
        config.postgres_user,
        "-d",
        config.postgres_db,
        "-Fc",
    ]
    with dump_path.open("wb") as output:
        process = subprocess.run(
            command,
            cwd=ROOT_DIR,
            stdout=output,
            stderr=subprocess.PIPE,
            check=False,
        )
    if process.returncode != 0:
        raise BackupError("postgres_dump", sanitize_text(process.stderr.decode("utf-8", "ignore")))
    if dump_path.stat().st_size == 0:
        raise BackupError("postgres_dump", "postgres.dump is empty.")


def archive_uploads(config: BackupConfig, uploads_archive_path: Path) -> None:
    command = compose_base_command(config) + [
        "exec",
        "-T",
        "backend",
        "python",
        "-c",
        UPLOADS_STREAM_CODE,
    ]
    with uploads_archive_path.open("wb") as output:
        process = subprocess.run(
            command,
            cwd=ROOT_DIR,
            stdout=output,
            stderr=subprocess.PIPE,
            check=False,
        )
    if process.returncode != 0:
        error = sanitize_text(process.stderr.decode("utf-8", "ignore"))
        raise BackupError("uploads_archive", error)
    verify_tar_readable(uploads_archive_path, "uploads_archive")


def verify_tar_readable(path: Path, step: str) -> None:
    try:
        with tarfile.open(path, "r:gz") as archive:
            archive.getmembers()
    except (tarfile.TarError, OSError) as exc:
        raise BackupError(step, f"{path.name} is not readable: {exc}") from exc


def restore_verify(
    config: BackupConfig,
    dump_path: Path,
    uploads_archive_path: Path,
) -> dict[str, Any]:
    restore_db = f"telegram_shop_restore_check_{int(time.time())}"
    ensure_restore_database_name(restore_db)
    counts: dict[str, int] = {}
    try:
        drop_database(config, restore_db)
        create_database(config, restore_db)
        restore_dump(config, restore_db, dump_path)
        alembic_version = query_scalar(
            config,
            restore_db,
            "SELECT version_num FROM alembic_version LIMIT 1;",
            "restore_verify_alembic",
        )
        if not alembic_version:
            raise BackupError("restore_verify", "alembic_version exists but has no rows.")
        missing_tables = [
            table
            for table in KEY_TABLES
            if query_scalar(
                config,
                restore_db,
                f"SELECT to_regclass('public.{table}');",
                "restore_verify_tables",
            )
            in {"", "None", "null"}
        ]
        if missing_tables:
            raise BackupError(
                "restore_verify",
                "Restored database is missing key tables: " + ", ".join(missing_tables),
            )
        for table in KEY_TABLES:
            if table == "alembic_version":
                continue
            raw_count = query_scalar(
                config,
                restore_db,
                f"SELECT COUNT(*) FROM {table};",
                "restore_verify_counts",
            )
            counts[table] = int(raw_count or "0")
        verify_tar_readable(uploads_archive_path, "restore_verify_uploads")
        return {
            "status": "passed",
            "restore_database": restore_db,
            "alembic_version": alembic_version,
            "table_counts": counts,
        }
    finally:
        drop_database(config, restore_db)


def ensure_restore_database_name(name: str) -> None:
    if not RESTORE_DB_RE.fullmatch(name):
        raise BackupError("restore_verify", f"Unsafe restore database name: {name}")


def create_database(config: BackupConfig, restore_db: str) -> None:
    run_psql_admin(config, f"CREATE DATABASE {restore_db};", "restore_verify_create_db")


def drop_database(config: BackupConfig, restore_db: str) -> None:
    ensure_restore_database_name(restore_db)
    run_psql_admin(
        config,
        f"DROP DATABASE IF EXISTS {restore_db} WITH (FORCE);",
        "restore_verify_drop_db",
    )


def run_psql_admin(config: BackupConfig, sql: str, step: str) -> None:
    command = compose_base_command(config) + [
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        config.postgres_user,
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    run_command(command, step=step)


def restore_dump(config: BackupConfig, restore_db: str, dump_path: Path) -> None:
    command = compose_base_command(config) + [
        "exec",
        "-T",
        "postgres",
        "pg_restore",
        "-U",
        config.postgres_user,
        "-d",
        restore_db,
        "--no-owner",
    ]
    with dump_path.open("rb") as input_file:
        process = subprocess.run(
            command,
            cwd=ROOT_DIR,
            stdin=input_file,
            capture_output=True,
            check=False,
        )
    if process.returncode != 0:
        raise BackupError("restore_verify_pg_restore", sanitize_text(process.stderr.decode()))


def query_scalar(config: BackupConfig, database: str, sql: str, step: str) -> str:
    command = compose_base_command(config) + [
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        config.postgres_user,
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-tAc",
        sql,
    ]
    result = run_command(command, step=step)
    return str(result.stdout).strip()


def get_git_commit() -> str | None:
    try:
        result = run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_DIR,
            step="git_commit",
        )
    except BackupError:
        return None
    return str(result.stdout).strip() or None


def get_alembic_current(config: BackupConfig) -> str | None:
    command = compose_base_command(config) + ["exec", "-T", "backend", "alembic", "current"]
    try:
        result = run_command(command, step="alembic_current")
    except BackupError:
        return None
    return " ".join(str(result.stdout).split()) or None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(work_dir: Path) -> Path:
    checksum_path = work_dir / "checksums.sha256"
    lines = [f"{sha256_file(work_dir / filename)}  {filename}\n" for filename in CHECKSUM_FILENAMES]
    checksum_path.write_text("".join(lines), encoding="utf-8")
    return checksum_path


def verify_checksums(work_dir: Path) -> None:
    checksum_path = work_dir / "checksums.sha256"
    expected: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, filename = line.split(maxsplit=1)
        expected[filename.strip()] = digest
    for filename, digest in expected.items():
        actual = sha256_file(work_dir / filename)
        if actual != digest:
            raise BackupError("checksums", f"Checksum mismatch for {filename}.")


def create_final_archive(work_dir: Path, archive_path: Path) -> None:
    backup_id = work_dir.name
    with tarfile.open(archive_path, "w:gz") as archive:
        for filename in (*CHECKSUM_FILENAMES, "checksums.sha256"):
            archive.add(work_dir / filename, arcname=f"{backup_id}/{filename}")
    verify_tar_readable(archive_path, "final_archive")


def list_local_backups(local_dir: Path) -> list[BackupObject]:
    backups: list[BackupObject] = []
    if not local_dir.exists():
        return backups
    for path in local_dir.glob("telegram-shop-*.tar.gz"):
        match = ARCHIVE_RE.match(path.name)
        if not match:
            continue
        backups.append(
            BackupObject(
                name=path.name,
                path=str(path),
                created_at=parse_backup_stamp(match.group("stamp")),
                size=path.stat().st_size,
            )
        )
    return backups


def parse_backup_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)


def parse_remote_datetime(value: Any) -> datetime:
    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed.astimezone(UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def select_retention_deletes(
    backups: Iterable[BackupObject],
    *,
    current_name: str,
    now: datetime,
    max_count: int,
    retention_days: int,
) -> list[BackupObject]:
    sorted_backups = sorted(backups, key=lambda item: item.created_at, reverse=True)
    cutoff = now - timedelta(days=retention_days)
    delete_names = {
        backup.name
        for backup in sorted_backups
        if backup.name != current_name and backup.created_at < cutoff
    }

    remaining = [backup for backup in sorted_backups if backup.name not in delete_names]
    while len(remaining) > max_count:
        candidate_index = next(
            (
                index
                for index in range(len(remaining) - 1, -1, -1)
                if remaining[index].name != current_name
            ),
            None,
        )
        if candidate_index is None:
            break
        candidate = remaining[candidate_index]
        delete_names.add(candidate.name)
        remaining.pop(candidate_index)

    return [backup for backup in sorted_backups if backup.name in delete_names]


def cleanup_local_retention(config: BackupConfig, current_archive_name: str) -> str:
    backups = list_local_backups(config.local_dir)
    to_delete = select_retention_deletes(
        backups,
        current_name=current_archive_name,
        now=datetime.now(UTC),
        max_count=config.retention_max_count,
        retention_days=config.retention_days,
    )
    for backup in to_delete:
        Path(backup.path).unlink(missing_ok=True)
    cleanup_old_work_dirs(config.local_dir, current_archive_name.removesuffix(".tar.gz"))
    return f"deleted {len(to_delete)} local archive(s)"


def cleanup_old_work_dirs(local_dir: Path, current_backup_id: str) -> None:
    for path in local_dir.glob("telegram-shop-*"):
        if not path.is_dir() or path.name == current_backup_id:
            continue
        if BACKUP_ID_RE.match(path.name):
            shutil.rmtree(path, ignore_errors=True)


def cleanup_remote_retention(
    client: YandexDiskClient,
    config: BackupConfig,
    current_archive_name: str,
) -> str:
    backups = client.list_backups(config.remote_dir)
    to_delete = select_retention_deletes(
        backups,
        current_name=current_archive_name,
        now=datetime.now(UTC),
        max_count=config.retention_max_count,
        retention_days=config.retention_days,
    )
    for backup in to_delete:
        client.delete(backup.path)
    return f"deleted {len(to_delete)} remote archive(s)"


def upload_backup_archive(
    client: YandexDiskClient,
    archive_path: Path,
    remote_path: str,
) -> dict[str, Any]:
    try:
        return client.upload_file(archive_path, remote_path)
    except YandexDiskError as exc:
        message = sanitize_text(str(exc), configured_secret_values())
        raise BackupError("yandex_upload", message) from exc


def build_notification_message(result: BackupRunResult) -> str:
    lines = [
        "Telegram Shop Platform backup",
        f"backup_id: {result.backup_id}",
        f"environment: {result.environment}",
        f"status: {result.status}",
        f"restore_verification: {result.restore_verification_status}",
        f"remote_path: {result.remote_path or 'not_available'}",
        f"archive_size: {format_bytes(result.archive_size)}",
        f"local_retention: {result.local_retention_result}",
        f"remote_retention: {result.remote_retention_result}",
    ]
    if result.failed_step:
        lines.append(f"failed_step: {result.failed_step}")
    if result.error:
        lines.append(f"error: {sanitize_text(result.error, configured_secret_values())}")
    return sanitize_text("\n".join(lines), configured_secret_values())


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MiB"
    return f"{size / (1024 * 1024 * 1024):.1f} GiB"


def notify(config: BackupConfig, result: BackupRunResult) -> None:
    if not config.telegram_notifications_enabled:
        return
    if not config.telegram_bot_token or not config.telegram_seller_chat_id:
        return
    notifier = TelegramNotifier(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_seller_chat_id,
    )
    notifier.send(build_notification_message(result))


def run_backup(args: argparse.Namespace) -> int:
    env = load_env_file(args.env_file)
    config = BackupConfig.from_mapping(env, env_file=args.env_file, compose_file=args.compose_file)
    if not config.backup_enabled:
        print("Backup is disabled by BACKUP_ENABLED=false.")
        return 0

    errors, warnings = config.validate(require_yandex=not args.skip_remote_upload)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        backup_id = generate_backup_id(datetime.now(UTC), config.environment)
        result = BackupRunResult(
            backup_id=backup_id,
            environment=config.environment,
            status="failed",
            failed_step="config_validation",
            error="; ".join(errors),
            restore_verification_status="not_run",
        )
        notify(config, result)
        return 1

    created_at = datetime.now(UTC).replace(microsecond=0)
    backup_id = generate_backup_id(created_at, config.environment)
    work_dir = config.local_dir / backup_id
    archive_path = config.local_dir / f"{backup_id}.tar.gz"
    remote_path = build_yandex_remote_path(config.remote_dir, archive_path.name)
    result = BackupRunResult(
        backup_id=backup_id,
        environment=config.environment,
        remote_path=remote_path,
    )

    try:
        config.local_dir.mkdir(parents=True, exist_ok=True)
        if work_dir.exists() or archive_path.exists():
            raise BackupError("backup_id", f"Backup already exists: {backup_id}")
        work_dir.mkdir(parents=True)

        dump_postgres(config, work_dir / "postgres.dump")
        archive_uploads(config, work_dir / "uploads.tar.gz")

        restore_info = restore_verify(
            config,
            work_dir / "postgres.dump",
            work_dir / "uploads.tar.gz",
        )
        result.restore_verification_status = str(restore_info["status"])
        if result.restore_verification_status != "passed":
            raise BackupError("restore_verify", "Restore verification did not pass.")

        metadata = create_backup_metadata(
            backup_id=backup_id,
            created_at=created_at,
            environment=config.environment,
            git_commit=get_git_commit(),
            alembic_current=get_alembic_current(config),
            compose_file=config.compose_file,
            restore_status=result.restore_verification_status,
            remote_path=remote_path,
        )
        write_json(work_dir / "backup_metadata.json", metadata)
        write_checksums(work_dir)
        verify_checksums(work_dir)
        create_final_archive(work_dir, archive_path)
        result.archive_size = archive_path.stat().st_size

        if args.skip_remote_upload:
            result.status = "warning_local_verified_only"
            result.remote_retention_result = "skipped"
        else:
            client = YandexDiskClient(
                client_id=config.yandex_client_id or "",
                client_secret=config.yandex_client_secret or "",
                refresh_token=config.yandex_refresh_token or "",
            )
            upload_backup_archive(client, archive_path, remote_path)
            result.remote_retention_result = cleanup_remote_retention(
                client,
                config,
                archive_path.name,
            )
            result.status = "success"

        result.local_retention_result = cleanup_local_retention(config, archive_path.name)
        shutil.rmtree(work_dir, ignore_errors=True)
        notify(config, result)
        print(build_notification_message(result))
        return 0
    except BackupError as exc:
        result.status = "failed"
        result.failed_step = exc.step
        result.error = sanitize_text(str(exc), configured_secret_values(env))
        package_failed_backup(work_dir, archive_path, result, config, created_at, remote_path)
        notify(config, result)
        print(build_notification_message(result), file=sys.stderr)
        return 1
    except Exception as exc:
        result.status = "failed"
        result.failed_step = "unexpected"
        result.error = sanitize_text(str(exc), configured_secret_values(env))
        package_failed_backup(work_dir, archive_path, result, config, created_at, remote_path)
        notify(config, result)
        print(build_notification_message(result), file=sys.stderr)
        return 1


def package_failed_backup(
    work_dir: Path,
    archive_path: Path,
    result: BackupRunResult,
    config: BackupConfig,
    created_at: datetime,
    remote_path: str,
) -> None:
    if not work_dir.exists():
        return
    try:
        metadata = create_backup_metadata(
            backup_id=result.backup_id,
            created_at=created_at,
            environment=config.environment,
            git_commit=get_git_commit(),
            alembic_current=None,
            compose_file=config.compose_file,
            restore_status=result.restore_verification_status
            if result.restore_verification_status != "pending"
            else "failed",
            remote_path=f"{remote_path} (not uploaded; backup failed or unverified)",
        )
        metadata["failure"] = {
            "status": "failed",
            "failed_step": result.failed_step,
            "error": sanitize_text(result.error or "", configured_secret_values()),
        }
        for filename in ("postgres.dump", "uploads.tar.gz"):
            if not (work_dir / filename).exists():
                (work_dir / filename).write_bytes(b"")
        write_json(work_dir / "backup_metadata.json", metadata)
        write_checksums(work_dir)
        verify_checksums(work_dir)
        create_final_archive(work_dir, archive_path)
        result.archive_size = archive_path.stat().st_size
    except Exception:
        return


def run_validate_config(args: argparse.Namespace) -> int:
    env = load_env_file(args.env_file)
    config = BackupConfig.from_mapping(env, env_file=args.env_file, compose_file=args.compose_file)
    errors, warnings = config.validate(require_yandex=args.strict_yandex)
    for warning in warnings:
        print(f"warning: {warning}")
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    print("Backup configuration is valid.")
    print(f"environment: {config.environment}")
    print(f"local_dir: {config.local_dir}")
    print(f"remote_dir: {normalize_remote_dir(config.remote_dir)}")
    print(f"retention: {config.retention_days} day(s), max {config.retention_max_count}")
    print(f"restore_verification_enabled: {config.restore_verify_enabled}")
    return 0


def run_list_remote(args: argparse.Namespace) -> int:
    env = load_env_file(args.env_file)
    config = BackupConfig.from_mapping(env, env_file=args.env_file, compose_file=args.compose_file)
    errors, warnings = config.validate(require_yandex=True)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    client = YandexDiskClient(
        client_id=config.yandex_client_id or "",
        client_secret=config.yandex_client_secret or "",
        refresh_token=config.yandex_refresh_token or "",
    )
    for backup in client.list_backups(config.remote_dir):
        print(f"{backup.created_at.isoformat()} {format_bytes(backup.size)} {backup.path}")
    return 0


def run_verify_archive(args: argparse.Namespace) -> int:
    archive_path = args.archive
    try:
        verify_tar_readable(archive_path, "verify_archive")
        with tarfile.open(archive_path, "r:gz") as archive:
            members = {member.name for member in archive.getmembers()}
        required = {"postgres.dump", "uploads.tar.gz", "backup_metadata.json", "checksums.sha256"}
        member_basenames = {Path(member).name for member in members}
        missing = required - member_basenames
        if missing:
            print("Archive is missing: " + ", ".join(sorted(missing)), file=sys.stderr)
            return 1
    except BackupError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Archive is readable: {archive_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Production backup automation.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Backend production env file. Defaults to backend/.env.production.",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=DEFAULT_COMPOSE_FILE,
        help="Production compose file. Defaults to docker-compose.prod.yml.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Create, verify, upload, and retain backup.")
    run_parser.add_argument(
        "--skip-remote-upload",
        action="store_true",
        help="Create and restore-verify a local backup without uploading to Yandex Disk.",
    )

    validate_parser = subparsers.add_parser("validate-config", help="Validate backup config.")
    validate_parser.add_argument(
        "--strict-yandex",
        action="store_true",
        help="Treat missing Yandex credentials as validation errors.",
    )

    verify_parser = subparsers.add_parser("verify-archive", help="Verify archive readability.")
    verify_parser.add_argument("archive", type=Path)

    subparsers.add_parser("list-remote", help="List remote Yandex Disk backup archives.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_backup(args)
    if args.command == "validate-config":
        return run_validate_config(args)
    if args.command == "verify-archive":
        return run_verify_archive(args)
    if args.command == "list-remote":
        return run_list_remote(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
