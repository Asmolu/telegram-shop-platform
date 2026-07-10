# Backup Strategy

StyleXac backups protect the PostgreSQL source of truth and uploaded files. The strategy is operationally tied to the production server at Aeza Frankfurt.

## Goals

- Recover from failed migrations.
- Recover from accidental data deletion.
- Recover uploaded images and payment receipts referenced by database rows.
- Preserve enough deploy metadata to understand which application version produced the data.
- Avoid exposing production secrets in backup logs or documentation.

## Production Backup Entry Point

Use the systemd service:

```bash
ssh tsplatform-frankfurt
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 160 --no-pager
```

Normal production operations must use the service, not a bare Python command.

## Backup Contents

| Item | Required | Notes |
| --- | --- | --- |
| PostgreSQL dump | Yes | Contains users, orders, catalog, coupons, subscriptions, campaigns, audit logs |
| Uploads archive | Yes | Contains product, banner, category, tag, review, campaign, receipt, and temporary upload folders |
| Commit hash | Yes | Identifies application version |
| Alembic revision | Yes | Current production head is `20260703_0047` |
| Compose file name | Yes | Production uses `docker-compose.prod.yml` |
| Env values | No | Store secrets only in the secure production secret location |

## Backup Schedule

Production scheduled policy:

- `telegram-shop-backup.timer` runs once per day at `04:00 Europe/Moscow`.
- The systemd template uses `OnCalendar=*-*-* 04:00:00 Europe/Moscow`.
- If a host systemd version cannot use timezone-aware `OnCalendar`, Moscow time is UTC+03:00 year-round, so the UTC fallback is `OnCalendar=*-*-* 01:00:00 UTC`.
- Manual backups before migrations still use `sudo systemctl start telegram-shop-backup.service`.

Operational triggers:

| Trigger | Action |
| --- | --- |
| Before Alembic migration | Run backup and verify service status |
| Before major deploy | Run backup when database or uploads are affected |
| Daily production routine | Ensure scheduled backup completed successfully |
| Before manual data repair | Run backup and save incident context |
| After restore drill | Record restore result and any missing steps |

## Retention

Current retention policy:

- Local archives are kept for 3 days.
- Yandex Disk archives are kept for 14 days with a count guard of 2 archives.
- Cleanup excludes the archive created by the current run.
- Remote cleanup runs only after a remote upload is sent successfully.

## Remote Upload Cadence

Every backup is created and restore-verified locally. Yandex Disk upload is intentionally sparse:

- Backups 1-6: local only.
- Backup 7: local plus Yandex Disk.
- Backups 8-13: local only.
- Backup 14: local plus Yandex Disk.

The script stores cadence state in `backup_state.json` under `BACKUP_LOCAL_DIR`. The state includes `successful_local_backup_count_since_last_remote`, `pending_remote_upload`, and `last_remote_upload_at`.

If the seventh remote upload fails after retries, the local backup still counts as created. The state keeps `pending_remote_upload=true`, and the next daily backup retries the remote upload as the pending seventh remote backup instead of waiting for backup 14.

## Verification

For every critical backup, verify:

- systemd service exited successfully
- PostgreSQL dump exists and is non-empty
- uploads archive exists and is non-empty
- backup metadata includes commit and Alembic revision
- backup logs do not contain raw secrets

Use:

```bash
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 160 --no-pager
```

Yandex Disk upload may occasionally timeout and retry. Treat the daily backup as locally successful when the local status is successful and restore verification passed; inspect the remote upload status separately as `skipped`, `sent`, or `failed`.

## Telegram Notifications

Backup notifications are sent every run and routed only to `TELEGRAM_BACKUP_CHAT_ID` with `TELEGRAM_BOT_TOKEN`. `TELEGRAM_SELLER_CHAT_ID` remains a legacy fallback when the backup chat id is absent. Backup notifications must not be routed to the orders or returns chats.

Each notification includes the backup id, local backup status, remote upload status (`skipped`, `sent`, or `failed`), restore verification status, archive size, local cleanup count, and remote cleanup count.

## Restore Testing

A restore drill should validate:

- database restore into an isolated environment
- uploads extraction into an isolated directory or volume
- backend startup against restored data
- `alembic current`
- API `/health`
- sample product image rendering
- Seller Panel login and product list load
- Mini App product list load

Do not run restore drills against production unless executing an approved incident response plan.

## Security

- Backups must be private.
- Backup logs must not include raw env values.
- Real bot tokens, DB passwords, JWT secrets, Yandex Disk tokens, private keys, and production credentials must not appear in documentation.
- Use placeholders in examples: `<SECRET>`, `<BOT_TOKEN>`, `<DATABASE_URL>`, `<JWT_SECRET>`.
