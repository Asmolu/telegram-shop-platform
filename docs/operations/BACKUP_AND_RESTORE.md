# Backup and restore

## Current policy in code

Timer intent: daily 04:00 Europe/Moscow. Script creates PostgreSQL custom dump, uploads tar,
metadata and SHA-256 checksums; restore-verifies into a temporary database; produces
`telegram-shop-<environment>-YYYYMMDD-HHMMSS.tar.gz`. Lock: `.backup_production.lock`; state:
`backup_state.json` in local backup dir.

| Policy | Value |
| --- | --- |
| Local cadence | 24 hours |
| Local retention | 3 days, max 20 |
| Remote cadence | every 7 successful local backups or pending retry |
| Remote retention | 14 days, max 2 |
| Restore verification | required by production policy |
| Remote provider | Yandex Disk when OAuth configured |

Remote `skipped` does not invalidate a verified local archive but means no new offsite copy from that
run. Remote failure sets pending retry. Replication, backup, offsite copy and restore verification are
different controls; PostgreSQL/Redis volumes are not backups by themselves.

## Manual backup

Canonical production action is starting the installed unit and reviewing status/journal:

```bash
sudo systemctl start telegram-shop-backup.service
sudo systemctl status telegram-shop-backup.service --no-pager
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
```

Repository unit path is stale. Verify installed unit before relying on reinstall.

## Restore outline

1. Declare incident and protect original volumes/archives.
2. Select archive; verify filename, readability, members and checksums.
3. Provision isolated PostgreSQL target and uploads location.
4. Restore dump and uploads; never overwrite production first.
5. Run Alembic current/schema checks and application smoke against isolated target.
6. Obtain incident commander approval for cutover.
7. Cut over, verify health, auth, catalog, order/payment/return and uploads.
8. Record data cutoff, archive id, results and follow-up.

Script `verify-local` creates/restores a local check without remote upload; `verify-archive` validates
archive structure. Exact CLI: `backend/scripts/backup_production.py --help`.

RPO: `NEEDS BUSINESS DECISION`. RTO: `NEEDS BUSINESS DECISION`. Owner/business approval is required;
both block SLA/DR claims.

Sources: backup script and systemd templates.

