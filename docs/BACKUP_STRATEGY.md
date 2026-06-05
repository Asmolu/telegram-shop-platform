# Production Backup Strategy

This document defines the implemented MVP backup strategy for the single-node
Docker Compose production profile on the VDS serving `tsplatform.ru`.

## Goals

- Protect PostgreSQL business data, the system source of truth.
- Protect uploaded product, banner, review, and temporary files stored in the
  production uploads volume.
- Keep offsite copies in Yandex Disk so VDS loss is recoverable.
- Automatically restore-verify every backup before it is marked successful.
- Notify the existing seller/admin chat through Bot 2.
- Keep secrets out of backups, logs, metadata, git, and Telegram messages.

## Non-Goals

- No high availability.
- No live PostgreSQL replication.
- No Redis durability guarantee; Redis is cache and rate-limit state only.
- No backup storage in Telegram.
- No automatic pre-deploy backup hook in this MVP task.
- No backup archive encryption in this MVP task.
- No plain `.env.production` backup inside normal archives.

## Assets Backed Up

Each backup includes:

- `postgres.dump`: PostgreSQL custom-format logical dump from the production
  `postgres` Compose service.
- `uploads.tar.gz`: archive of `/app/uploads` from the backend service with
  relative paths preserved.
- `backup_metadata.json`: non-secret metadata only.
- `checksums.sha256`: SHA-256 checksums for `postgres.dump`,
  `uploads.tar.gz`, and `backup_metadata.json`.

Each backup excludes:

- `backend/.env.production`
- Telegram bot tokens
- Yandex OAuth tokens
- database passwords
- JWT and webhook secrets
- private keys
- Redis data
- raw logs or stack traces

Production secrets must be recoverable from a password manager, secure operator
vault, or a separately encrypted secret backup.

## Archive Layout

Working directory:

```text
backups/
  telegram-shop-prod-YYYYMMDD-HHMMSS/
    postgres.dump
    uploads.tar.gz
    backup_metadata.json
    checksums.sha256
```

Final archive:

```text
telegram-shop-prod-YYYYMMDD-HHMMSS.tar.gz
```

The archive keeps the timestamped directory as its top-level entry.

## Metadata

`backup_metadata.json` includes only non-secret values:

- backup id
- UTC creation time
- environment
- deployed git commit if available
- current Alembic revision if available
- Compose file name
- payload filenames
- restore verification status
- Yandex Disk provider/path
- checksum filename
- notes that secrets and Redis data are not stored

Metadata must never include `.env.production` values, tokens, passwords,
private keys, signed URLs, webhook secrets, or database connection strings.

## Verification

Every normal run must pass automatic restore verification before the archive is
uploaded as successful.

The script:

1. Creates a temporary PostgreSQL database named
   `telegram_shop_restore_check_<timestamp>`.
2. Restores `postgres.dump` into that temporary database.
3. Verifies `alembic_version` exists and has a revision row.
4. Verifies key commerce tables exist.
5. Runs basic count queries against key tables.
6. Verifies `uploads.tar.gz` can be listed.
7. Drops the temporary database.

The production database is never used as the restore target. If verification
fails, the backup is failed and no successful Yandex upload is performed.

## Offsite Target

Yandex Disk is the MVP offsite target:

```text
/TelegramShopPlatform/storage/
```

The script uses Yandex OAuth with `YANDEX_CLIENT_ID`,
`YANDEX_CLIENT_SECRET`, and `YANDEX_REFRESH_TOKEN` from
`backend/.env.production`. It exchanges the refresh token for a short-lived
access token, creates the remote directory if needed, uploads the final archive,
and verifies remote metadata size after upload.

Access tokens and refresh tokens are never logged, stored in metadata, or sent
to Telegram.

## Schedule and Retention

MVP policy:

- Run every 6 hours.
- Keep backups for 5 days.
- Keep at most 20 local archives.
- Keep at most 20 Yandex Disk archives.
- Never delete the current backup during retention cleanup.

The systemd timer template uses:

```text
OnUnitActiveSec=6h
Persistent=true
```

Retention failures are warnings if dump creation, restore verification, and
Yandex upload already succeeded.

## Notifications

Bot 2 sends backup status to the existing seller/admin chat using:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_SELLER_CHAT_ID
```

Notifications include:

- backup id
- environment
- status
- failed step when applicable
- restore verification status
- remote path
- archive size
- local and remote retention result

Notification text is sanitized. It must not include raw secret values, bot
tokens, OAuth tokens, database passwords, `.env.production`, private keys,
signed URLs, or raw exception traces.

## Operational Commands

Validate production configuration:

```bash
python backend/scripts/backup_production.py validate-config --strict-yandex
```

Run a full backup:

```bash
python backend/scripts/backup_production.py run
```

Run a local verified dry run without Yandex upload:

```bash
python backend/scripts/backup_production.py run --skip-remote-upload
```

List remote archives:

```bash
python backend/scripts/backup_production.py list-remote
```

Systemd template files:

```text
scripts/systemd/telegram-shop-backup.service
scripts/systemd/telegram-shop-backup.timer
```

## Restore Strategy

Restores are manual in MVP and should be drilled regularly in staging or an
isolated VDS.

High-level restore flow:

1. Select a verified archive from Yandex Disk or local backups.
2. Verify archive readability and checksums.
3. Recreate production secrets from the secure secret source; they are not in
   the archive.
4. Stop or isolate backend writes.
5. Restore `postgres.dump` into a clean PostgreSQL database.
6. Restore `uploads.tar.gz` into `uploads_data`.
7. Compare `alembic current` with `backup_metadata.json`.
8. Decide whether to run migrations forward for the deployed code.
9. Restart Compose services.
10. Run backend, Mini App, and Seller Panel smoke checks.

See `docs/BACKUP_AND_RESTORE.md` for exact commands.

## Failure Modes

- PostgreSQL dump failure: backup fails; do not treat uploads-only artifacts as
  successful.
- Upload archive failure: backup fails because database paths may reference
  files that were not protected.
- Restore verification failure: backup fails and is not uploaded as successful.
- Yandex upload failure: backup fails as offsite protection did not complete;
  the verified local archive remains for operator inspection.
- Retention cleanup failure after successful upload: backup reports warning.
- Telegram notification failure: log locally; it does not invalidate the
  backup artifact.

## Open Follow-Ups

- Add encrypted secret backup or document the external password-manager
  procedure in more detail.
- Add monthly restore-drill records once the VDS schedule is active.
- Consider S3-compatible storage if lifecycle policies or reliability require
  a second offsite target.
