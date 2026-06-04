# Production Backup Strategy

This document defines the production backup and restore strategy for the
single-node Docker Compose production profile on a VDS. It is a design document
only. It does not implement scripts, add dependencies, or change application,
Docker, migration, or environment files.

## 1. Goals

- Protect PostgreSQL data, which is the source of truth for business data.
- Protect uploaded product, banner, review, and temporary files stored in the
  production uploads volume.
- Support recovery after total VDS loss, bad deployment, bad migration,
  accidental file loss, operator error, and partial local disk failure.
- Support both manual backup flows before risky operations and automated daily
  backup flows.
- Keep backup artifacts verifiable, portable, and independent of the running
  application code.
- Keep offsite copies because local access to the VDS can fail.

## 2. Non-goals

- No high availability.
- No live PostgreSQL replication.
- No Kubernetes.
- No automated restore in the MVP.
- No plain-text `.env.production` or secret backup to Telegram.
- No use of Telegram as the only or primary backup storage.
- No backup of Redis as durable business data; Redis is cache/rate-limit state
  and can be rebuilt.

## 3. Assets To Back Up

Required production assets:

- PostgreSQL logical dump from the `postgres` service.
- Uploads directory/volume mounted as `uploads_data` and available to the
  backend at `/app/uploads`.
- Backup metadata describing when, where, and how the backup was created.
- Git commit hash of the deployed repository revision.
- Alembic current revision at backup time.
- Docker Compose file hash/checksum for `docker-compose.prod.yml`.
- Checksums for all backup payload files.

Recommended metadata:

- Application environment name, for example `production` or `staging`.
- Docker image ids or tags for backend, Mini App, Seller Panel, PostgreSQL, and
  Redis when available.
- PostgreSQL database name and user name only, not the password.
- Upload volume name and source path.
- Backup command/tool version.
- Sanitized environment key list without values, so missing configuration can
  be noticed during restore without exposing secrets.

Secrets and `.env.production`:

- `backend/.env.production` is operationally critical but must not be included
  in a plain backup archive by default.
- Store production secrets in a password manager, secure operator vault, or a
  separately encrypted secret backup.
- If `.env.production` must be backed up, it must be encrypted before leaving
  the VDS and must never be sent to Telegram in plain text.
- Telegram bot tokens, JWT secrets, webhook secrets, database passwords, Yandex
  Disk tokens, Sentry DSNs, and private keys are secret values and must not
  appear in logs, backup metadata, notification text, or unencrypted archives.

## 4. Backup Archive Structure

Each backup should produce a timestamped directory first, then a single archive
for retention and upload.

Suggested working directory:

```text
backups/
  telegram-shop-prod-YYYYMMDD-HHMMSS/
    postgres.dump
    uploads.tar.gz
    backup_metadata.json
    checksums.sha256
```

Suggested final archive:

```text
telegram-shop-prod-YYYYMMDD-HHMMSS.tar.gz
```

`backup_metadata.json` should include only non-secret values:

```json
{
  "backup_id": "telegram-shop-prod-YYYYMMDD-HHMMSS",
  "created_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
  "environment": "production",
  "git_commit": "placeholder",
  "alembic_current": "placeholder",
  "compose_file": "docker-compose.prod.yml",
  "compose_sha256": "placeholder",
  "postgres_dump_format": "custom",
  "uploads_archive": "uploads.tar.gz",
  "env_keys_present": ["APP_ENV", "DATABASE_URL", "JWT_SECRET_KEY"],
  "notes": "No secret values are stored in metadata."
}
```

## 5. Backup Formats

PostgreSQL:

- Prefer PostgreSQL custom format (`pg_dump -Fc`) for MVP backups.
- Custom dumps support `pg_restore --list`, selective restore inspection, and
  cleaner restore workflows than plain SQL.
- Plain SQL dumps are useful for manual inspection, but they are larger, less
  flexible, and slower to selectively restore.
- Do not rely on filesystem-level copies of the PostgreSQL data volume for MVP
  backups unless the database is stopped and the process is documented
  separately.

Uploads:

- Use `tar.gz` for uploads because the production data is a directory tree in a
  Docker volume.
- Preserve paths relative to the uploads root.
- Do not store uploaded files in PostgreSQL. PostgreSQL stores only paths/URLs.

Final archive:

- Package `postgres.dump`, `uploads.tar.gz`, `backup_metadata.json`, and
  `checksums.sha256` into a final `tar.gz` archive.
- Generate checksums before upload and verify them after download.

Encryption:

- Optional in Phase 3, strongly recommended before storing secret archives or
  sending any backup file through a chat channel.
- Prefer recipient-based encryption, for example age/GPG, over a shared
  passphrase when multiple operators need access.
- If passphrase encryption is used, read the passphrase from a protected file or
  secret manager, not from command-line arguments or logs.

## 6. Storage Targets

Local server backup directory:

- Use a local directory such as `./backups` on the VDS as the first landing
  area.
- Keep it outside git and ensure it is excluded from commits.
- Treat it as short-term fallback only. It does not protect against VDS loss.
- Restrict permissions to the deployment user and backup operator group.

Yandex Disk:

- Use Yandex Disk as the primary offsite target for MVP.
- Store production backups under a dedicated app path, for example
  `/TelegramShopPlatform/production/`.
- Upload the final archive and a small sidecar status/metadata file if useful.
- Verify upload completion and remote size/checksum where the API allows it.
- Keep the Yandex Disk token as a backend/server secret, not in git and not in
  notification text.

Telegram:

- Use Telegram as a notification channel only.
- Notification content may include backup id, status, size, retention result,
  and masked target names.
- Notification content must not include secrets, tokens, database passwords,
  raw `.env.production`, signed URLs, or full chat IDs when masking is
  practical.
- Telegram is not reliable long-term backup storage and must not be the only
  offsite copy.
- Optional Telegram file upload is allowed only for small encrypted archives or
  small encrypted metadata bundles. This should stay disabled by default.

Optional future target:

- S3-compatible storage such as Cloudflare R2 can be added later if Yandex Disk
  reliability, lifecycle rules, or automation become limiting.

## 7. Retention Policy

Recommended MVP retention:

- Local VDS backups: daily backups, keep last 7.
- Yandex Disk offsite backups: keep daily 14, weekly 4, monthly 3.
- Keep at least one manual pre-deploy backup until the deployment is confirmed
  healthy and the next scheduled backup succeeds offsite.

Justification:

- The local last-7 window gives quick recovery for recent mistakes without
  consuming too much VDS disk.
- The offsite 14/4/3 policy gives short-term rollback depth, weekly coverage for
  slower discoveries, and three monthly recovery anchors after VDS loss.
- If uploads grow quickly, retention cleanup must consider archive size and
  alert before disk pressure becomes critical.

Retention classes:

- `daily`: scheduled backup.
- `weekly`: first successful daily backup of the week.
- `monthly`: first successful daily backup of the month.
- `manual`: operator-created backup before deploy, migration, import, or
  storage change.

Manual backups should either expire with the same policy after explicit tagging
or be reviewed during weekly maintenance to avoid unbounded storage growth.

## 8. Scheduling

Manual backups:

- Create a manual backup before production deploys, Alembic migrations, data
  imports, bulk product changes, storage changes, or risky maintenance.
- A deploy or migration should not proceed if the pre-deploy backup fails local
  verification.
- A deploy may proceed if offsite upload fails only after an explicit operator
  decision, because this increases risk during VDS incidents.

Automated backups:

- Run daily scheduled backups during low-traffic hours.
- Prefer a `systemd` timer on the VDS for production scheduling because it
  provides logs, missed-run handling, and explicit service state.
- Cron is acceptable for MVP if the script logs clearly and sends failure
  notifications.
- Do not schedule inside the application backend process.

Overlap with deploys:

- Backups and deploys must use a lock so they do not run destructive or
  high-load operations at the same time.
- If a backup is running, deployment should wait or require an explicit
  operator override.
- If deployment is running, scheduled backup should skip or wait, then send a
  notification that the run was delayed.
- A migration should always have a fresh verified PostgreSQL dump before it
  starts.

## 9. Restore Strategy

Restore is manual in the MVP and should be practiced in staging before it is
needed in production.

High-level full restore flow:

1. Provision or regain access to a VDS with Docker and the repository.
2. Check out the target git commit from `backup_metadata.json`, or choose a
   newer compatible commit deliberately.
3. Recreate production environment files from the password manager or encrypted
   secret backup. Do not restore plain secrets from Telegram.
4. Download the selected backup archive from Yandex Disk or copy it from local
   backups.
5. Verify archive checksums before extracting.
6. Restore PostgreSQL from `postgres.dump` into a clean database.
7. Restore `uploads.tar.gz` into the `uploads_data` volume.
8. Check `alembic current` against `backup_metadata.json`.
9. If the application commit expects newer schema, run migrations deliberately
   after the database restore and record the decision.
10. Restart Docker Compose services.
11. Run smoke checks for backend health, public catalog, Mini App, Seller Panel,
    and critical upload URLs.

PostgreSQL restore principles:

- Restore into a clean database unless a partial restore plan has been approved.
- Use custom dump restore tooling for `postgres.dump`.
- Stop or isolate the backend during restore so users cannot write into a
  partially restored database.
- Confirm that order, product, user, audit, analytics, coupon usage, and
  notification tables are present after restore.

Uploads restore principles:

- Restore uploads into the production uploads volume before exposing the app.
- Preserve relative paths because PostgreSQL rows reference upload paths.
- If only uploads were lost, restore uploads from the same or nearest backup and
  compare missing file references against database rows.

Alembic verification:

- Compare restored database revision with `backup_metadata.json`.
- If revisions differ from the deployed code, decide whether to roll code back
  to the backup commit or migrate the restored database forward.
- Do not edit old migrations during restore.

Rollback from failed deploy:

- If a deploy fails before migrations, roll back application images/code and
  restart services.
- If a deploy fails after migrations but before writes from the new version,
  prefer restoring the pre-deploy database backup plus uploads if files changed.
- If the new version accepted writes, decide whether data loss is acceptable
  before restoring the pre-deploy backup. Otherwise fix forward or perform a
  targeted recovery.

## 10. Verification Strategy

Every backup run should verify:

- `checksums.sha256` exists and covers `postgres.dump`, `uploads.tar.gz`,
  `backup_metadata.json`, and the final archive.
- The final archive can be listed.
- `uploads.tar.gz` can be listed.
- PostgreSQL custom dump can be inspected with `pg_restore --list`.
- `backup_metadata.json` is valid JSON and contains backup id, git commit,
  Alembic current revision, and compose checksum.
- Local backup size is non-zero and within expected bounds.
- Offsite upload completed when enabled.

Periodic restore drills:

- Run a restore drill at least monthly for MVP, and before major launches.
- Restore into staging or an isolated temporary environment.
- Verify `/health`, public product/category/tag endpoints, representative
  product images, Seller Panel login, and one non-production test order flow.
- Record drill date, backup id, restore duration, issues found, and fixes.

Alerts:

- Send success notification after local verification and offsite upload both
  succeed.
- Send warning if local backup succeeds but Yandex Disk upload fails.
- Send failure if local backup, checksum generation, PostgreSQL dump, uploads
  archive, or verification fails.
- Telegram notification failure must be logged locally but must not mark the
  backup artifact itself invalid.

## 11. Security Model

Secret handling:

- Do not include `.env.production` in the default archive.
- If secret backup is required, encrypt it separately and store it separately
  from normal backup archives.
- Do not send unencrypted secrets to Telegram.
- Do not put secret values in `backup_metadata.json`, logs, retention reports,
  error messages, or chat notifications.
- Back up a sanitized env key list without values only.

Yandex Disk token:

- Store the token as a server-side secret with the minimum required scope.
- Restrict file permissions on any token file.
- Rotate the token if logs, screenshots, shell history, or operators may have
  exposed it.
- Never include the token in Telegram messages or backup metadata.

Telegram notifications:

- Include only status, backup id, duration, archive size, and masked destination
  names.
- Do not include signed download links unless they are short-lived and still do
  not expose secrets.
- Mask chat IDs where possible, for example show only the last 4 digits.

Local file permissions:

- Backup directory should be owned by the deploy/backup user.
- Use restrictive directory permissions, for example owner-only access where
  practical.
- Backup archives should not be world-readable.
- Keep backups, database dumps, uploaded user files, and secret files out of
  git.

## 12. Failure Modes

Docker unavailable:

- Backup cannot use Compose containers.
- Send failure notification if possible and log locally.
- Operator should inspect Docker daemon status and disk pressure.

PostgreSQL unavailable:

- PostgreSQL dump fails.
- Do not create a "successful" backup with only uploads unless explicitly
  tagged as partial.
- Alert that business data was not protected for this run.

Uploads directory or volume missing:

- Treat as failure unless the environment is explicitly known to have no
  uploads.
- Include missing path/volume name in local logs without exposing secrets.
- Investigate before deploy, because database rows may reference missing files.

Yandex Disk upload fails:

- Keep the verified local backup.
- Send warning notification.
- Retry with bounded attempts.
- Mark backup status as "local-only" until offsite upload succeeds.

Telegram notification fails:

- Keep backup result based on local/offsite verification.
- Log sanitized notification failure.
- Do not retry indefinitely.

Backup archive too large:

- Complete local backup if disk allows.
- Skip Telegram file upload even if enabled.
- Upload to Yandex Disk as the primary offsite target.
- Alert with archive size and retention pressure.

Disk full:

- Backup may fail while dumping, archiving, or generating checksums.
- Do not delete the newest known-good backup blindly.
- Apply retention cleanup to expired backups first, then retry.
- Alert immediately because production services may also be at risk.

VDS inaccessible:

- Use the latest verified Yandex Disk backup plus repository and secret source
  to restore on a new VDS.
- Local-only backups are unavailable in this scenario.
- This is the reason Yandex Disk offsite upload is required for production.

Bad backup discovered during restore:

- Stop restore and preserve the bad archive for investigation.
- Try the previous verified offsite backup.
- Compare checksums, metadata, and `pg_restore --list` output.
- Record the incident and increase restore drill frequency until the root cause
  is resolved.

## 13. Proposed Implementation Phases

Phase 1: manual local backup and restore documentation

- Add a manual backup script design for creating PostgreSQL custom dumps.
- Add uploads archive creation.
- Write backup metadata and checksums.
- Keep local backups in `BACKUP_DIR`.
- Document manual restore steps and smoke checks.

Phase 2: offsite upload and notifications

- Add Yandex Disk upload.
- Add Telegram notification for success, warning, and failure.
- Add retention cleanup for local and Yandex Disk backups.
- Mark backups as local-only if offsite upload fails.

Phase 3: scheduling and restore drill

- Add daily scheduling through `systemd` timer or cron.
- Add backup/deploy lock behavior.
- Perform and document the first restore drill.
- Add optional encryption for backup archives and required encryption for any
  secret backup.

Phase 4: monitoring and dashboard if needed

- Add richer monitoring/alerts for missed backups, local-only backups, storage
  pressure, and restore drill age.
- Add a backup status dashboard only if operational need justifies it.
- Consider S3-compatible storage if Yandex Disk lifecycle or reliability is not
  enough.

## 14. Proposed Environment Variables

Placeholders only. Do not put real values in documentation or git.

```text
BACKUP_DIR=/path/to/local/backups
BACKUP_RETENTION_LOCAL=7

YANDEX_DISK_BACKUP_ENABLED=false
YANDEX_DISK_TOKEN=<stored-outside-git>
YANDEX_DISK_BACKUP_PATH=/TelegramShopPlatform/production

BACKUP_TELEGRAM_NOTIFY_ENABLED=false
BACKUP_TELEGRAM_CHAT_ID=<masked-or-stored-outside-git>
BACKUP_TELEGRAM_SEND_FILE=false
BACKUP_MAX_TELEGRAM_FILE_MB=20

BACKUP_ENCRYPTION_ENABLED=false
BACKUP_ENCRYPTION_RECIPIENT=<recipient-id-or-public-key>
BACKUP_ENCRYPTION_PASSPHRASE_FILE=/path/to/protected/passphrase-file
```

Notes:

- `YANDEX_DISK_TOKEN` must be treated like a production secret.
- `BACKUP_TELEGRAM_CHAT_ID` should not be printed in full in logs or
  notifications.
- `BACKUP_TELEGRAM_SEND_FILE` should remain `false` unless the archive is small
  and encrypted.
- Use either `BACKUP_ENCRYPTION_RECIPIENT` or
  `BACKUP_ENCRYPTION_PASSPHRASE_FILE`, depending on the encryption approach.

## 15. Manual Commands Draft

Draft command names only. These commands do not exist yet.

```bash
scripts/backup_prod.py create
scripts/backup_prod.py verify
scripts/backup_prod.py upload
scripts/backup_prod.py list
scripts/restore_prod.py restore --file ...
```

Recommended future behavior:

- `create`: produce local backup directory, dump, uploads archive, metadata,
  checksums, and final archive.
- `verify`: validate checksums, archive listings, metadata, and PostgreSQL dump
  listing.
- `upload`: send verified archive to Yandex Disk and mark offsite status.
- `list`: show local/offsite backups, age, size, status, and retention class.
- `restore`: guide or perform a guarded manual restore from a selected archive.

## 16. Open Questions

- Should `.env.production` be backed up encrypted, or stored separately in a
  password manager only?
- Is Yandex Disk sufficient for MVP offsite storage, or should
  S3-compatible storage be used from the start?
- Is Telegram file upload allowed only for encrypted archives, or should it stay
  disabled entirely?
- How much restore downtime is acceptable for production?
- How often should restore drills be performed after MVP launch?
- Who receives backup failure notifications?
- What is the maximum acceptable data loss window: 24 hours, 12 hours, or less?
- Should manual pre-deploy backups have separate retention from scheduled daily
  backups?
- Who is allowed to run restore commands in production?
