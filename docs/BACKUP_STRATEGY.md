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
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
```

Normal production operations must use the service, not a bare Python command.

## Backup Contents

| Item | Required | Notes |
| --- | --- | --- |
| PostgreSQL dump | Yes | Contains users, orders, catalog, coupons, subscriptions, campaigns, audit logs |
| Uploads archive | Yes | Contains product, banner, category, tag, review, campaign, receipt, and temporary upload folders |
| Commit hash | Yes | Identifies application version |
| Alembic revision | Yes | Current production head is `20260628_0039` |
| Compose file name | Yes | Production uses `docker-compose.prod.yml` |
| Env values | No | Store secrets only in the secure production secret location |

## Backup Schedule

Recommended operational policy:

| Trigger | Action |
| --- | --- |
| Before Alembic migration | Run backup and verify service status |
| Before major deploy | Run backup when database or uploads are affected |
| Daily production routine | Ensure scheduled backup completed successfully |
| Before manual data repair | Run backup and save incident context |
| After restore drill | Record restore result and any missing steps |

## Retention

Use retention that covers:

- recent deploy rollback window
- weekly recovery window
- monthly compliance or business recovery window if required

The exact retention policy can be adjusted by storage cost and business requirements, but old backups must not be deleted until at least one newer backup has been restore-tested.

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
sudo journalctl -u telegram-shop-backup.service -n 120 --no-pager
```

## Telegram Notifications

Backup success/failure notifications are routed only to `TELEGRAM_BACKUP_CHAT_ID` with `TELEGRAM_BOT_TOKEN`. `TELEGRAM_SELLER_CHAT_ID` remains a legacy fallback when the backup chat id is absent. Backup notifications must not be routed to the orders or returns chats.

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
