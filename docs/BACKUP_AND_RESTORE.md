# Backup and Restore

Production backups are automated for the single-node VDS deployment under
`stylexac.ru`. PostgreSQL is the source of truth for business data. Uploaded
files live on disk in the `uploads_data` Docker volume and are backed up
separately. Redis is cache and rate-limit state only and is not backed up as
durable data.

The normal production target is Yandex Disk:

```text
/TelegramShopPlatform/storage/
```

Do not include `backend/.env.production`, tokens, database passwords, webhook
secrets, private keys, uploaded user files outside the uploads archive, or
database dumps in git.

## Backup Contents

Each run creates a timestamped working directory under `BACKUP_LOCAL_DIR`:

```text
backups/
  telegram-shop-prod-YYYYMMDD-HHMMSS/
    postgres.dump
    uploads.tar.gz
    backup_metadata.json
    checksums.sha256
```

The final local/offsite artifact is:

```text
telegram-shop-prod-YYYYMMDD-HHMMSS.tar.gz
```

`postgres.dump` is a PostgreSQL custom-format dump from the production
`postgres` service. `uploads.tar.gz` is an archive of `/app/uploads` from the
backend service with relative paths preserved. `backup_metadata.json` stores
only non-secret operational metadata, restore verification status, and the
Yandex Disk path. `.env.production` is not included.

## Required Environment

Set these in `backend/.env.production` on the VDS. Keep real values out of git;
only placeholders belong in example files.

```text
BACKUP_ENABLED=true
BACKUP_ENVIRONMENT=production
BACKUP_LOCAL_DIR=backups
BACKUP_REMOTE_DIR=/TelegramShopPlatform/storage
BACKUP_INTERVAL_HOURS=6
BACKUP_RETENTION_DAYS=5
BACKUP_RETENTION_MAX_COUNT=20
BACKUP_RESTORE_VERIFY_ENABLED=true

YANDEX_CLIENT_ID=
YANDEX_CLIENT_SECRET=
YANDEX_REFRESH_TOKEN=

BACKUP_TELEGRAM_NOTIFICATIONS_ENABLED=true
TELEGRAM_BOT_TOKEN=<Bot 2 token>
TELEGRAM_SELLER_CHAT_ID=<seller/admin chat id>
```

`YANDEX_REFRESH_TOKEN` is stored only in `backend/.env.production` on the VDS.
Telegram is notification-only and is never used as backup storage.

## CLI Commands

Run commands from the repository root on the VDS.

Validate configuration without requiring local Yandex credentials:

```bash
python backend/scripts/backup_production.py validate-config
```

Validate full VDS production configuration:

```bash
python backend/scripts/backup_production.py validate-config --strict-yandex
```

Run a full production backup, restore verification, Yandex upload, and
retention cleanup:

```bash
python backend/scripts/backup_production.py run
```

Run a local verified backup without Yandex upload for a dry run:

```bash
python backend/scripts/backup_production.py run --skip-remote-upload
```

Verify that an existing archive is readable:

```bash
python backend/scripts/backup_production.py verify-archive backups/telegram-shop-prod-YYYYMMDD-HHMMSS.tar.gz
```

List remote Yandex Disk backups:

```bash
python backend/scripts/backup_production.py list-remote
```

## Operational Safety

The mutating `run` command holds an exclusive Linux `flock` on
`BACKUP_LOCAL_DIR/.backup_production.lock`. A systemd-triggered run and a manual
run therefore cannot overlap. Lock contention exits non-zero before dump,
archive, upload, or retention work starts. The lock file may remain on disk;
the kernel lock is released automatically when the process exits.

Yandex API and upload requests use bounded HTTP timeouts: 20 seconds to
connect, 120 seconds to read, 300 seconds to write, and 20 seconds to acquire a
connection from the pool. Uploads use at most three attempts with short
backoff. Every attempt obtains a new signed upload URL, stats the closed local
archive, opens a new stream at byte zero, and sends an exact `Content-Length`.

After a timeout or transient transport failure, the script checks only the
current backup's exact remote path. An exact remote size is accepted as a
completed upload; a missing or mismatched object is overwritten on the next
attempt. Failed uploads keep the verified local archive and skip both local
and remote retention.

## Restore Verification

Every normal backup is restore-verified before it is marked successful or
uploaded to Yandex Disk.

The script creates a temporary database named
`telegram_shop_restore_check_<timestamp>`, restores `postgres.dump` into it,
checks that `alembic_version` and key commerce tables exist, runs basic count
queries, verifies `uploads.tar.gz` is readable, and then drops the temporary
database. It never restores into the production database.

If restore verification fails, the backup is marked failed, no successful
Yandex upload is performed, and Bot 2 sends a failure notification.

## Retention

The MVP retention policy is:

- Schedule: every 6 hours.
- Maximum age: 5 days.
- Maximum count: 20 archives locally and in Yandex Disk.

Retention cleanup never deletes the current archive. If backup creation,
restore verification, and upload succeed but retention cleanup fails, the
backup notification reports a warning.

## Telegram Notifications

Backup status notifications are sent through Bot 2 using:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_SELLER_CHAT_ID
```

Messages include backup id, environment, status, failed step, restore
verification status, remote path, archive size, and retention results. The
script sanitizes configured secret values, bot tokens, OAuth tokens, and long
secret-looking strings before sending errors. It never sends signed URLs,
refresh tokens, database passwords, `.env.production`, or raw exception traces.

## Install Systemd Timer

Template files live in:

```text
scripts/systemd/telegram-shop-backup.service
scripts/systemd/telegram-shop-backup.timer
```

The templates assume the repository is deployed to:

```text
/opt/TelegramShopPlatform
```

Adjust paths if the VDS uses a different deploy directory. The service expects
a Python environment with backend dependencies installed, for example:

```bash
cd /opt/TelegramShopPlatform/backend
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Install and enable the timer manually:

```bash
sudo cp /opt/TelegramShopPlatform/scripts/systemd/telegram-shop-backup.service /etc/systemd/system/
sudo cp /opt/TelegramShopPlatform/scripts/systemd/telegram-shop-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-shop-backup.timer
systemctl list-timers telegram-shop-backup.timer
```

Check logs:

```bash
journalctl -u telegram-shop-backup.service -n 100 --no-pager
```

Do not add automatic pre-deploy backup hooks for this MVP task.

## Manual Restore Drill

Practice restores in staging or an isolated VDS before relying on production
backups during an incident.

1. Download the selected archive from Yandex Disk or copy it from local
   `backups/`.
2. Run `python backend/scripts/backup_production.py verify-archive <archive>`.
3. Extract the archive and verify `checksums.sha256`.
4. Stop or isolate the backend so users cannot write during restore.
5. Restore `postgres.dump` into a clean database with `pg_restore`.
6. Restore `uploads.tar.gz` into the `uploads_data` volume.
7. Recreate `backend/.env.production` from the password manager or other secure
   secret source; it is not inside the backup archive.
8. Run `alembic current` and compare with `backup_metadata.json`.
9. Run migrations deliberately only if the restored database must be moved
   forward to the deployed code.
10. Restart Compose services and run smoke checks:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend alembic current
curl -i https://api.stylexac.ru/health
curl -i https://api.stylexac.ru/api/v1/products
curl -i https://stylexac.ru
curl -i https://www.stylexac.ru
curl -i https://mini.stylexac.ru
curl -i https://seller.stylexac.ru
```

For local VDS-only smoke checks, use `http://localhost:8000`,
`http://localhost:8080`, and `http://localhost:8081`.
