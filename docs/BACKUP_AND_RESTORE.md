# Backup and Restore

Back up both PostgreSQL and uploaded files. PostgreSQL is the source of truth for business data, while uploads are stored on disk and referenced by path.

## PostgreSQL Backup

Custom format backup:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec postgres pg_dump -U telegram_shop -d telegram_shop -Fc -f /backups/telegram_shop_$(date +%Y%m%d_%H%M%S).dump
```

Plain SQL backup:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec postgres pg_dump -U telegram_shop -d telegram_shop -f /backups/telegram_shop_$(date +%Y%m%d_%H%M%S).sql
```

Copy backup files from `./backups` to off-host storage after creation.

## PostgreSQL Restore

Restore custom format into an empty database:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec postgres pg_restore -U telegram_shop -d telegram_shop --clean --if-exists /backups/telegram_shop_YYYYMMDD_HHMMSS.dump
```

Restore plain SQL:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec -T postgres psql -U telegram_shop -d telegram_shop < ./backups/telegram_shop_YYYYMMDD_HHMMSS.sql
```

Run migrations after restoring if the application version expects a newer schema:

```bash
docker compose --env-file backend/.env.production -f docker-compose.prod.yml exec backend alembic upgrade head
```

## Uploads Backup

Archive the production uploads volume:

```bash
docker run --rm -v telegramshopplatform_uploads_data:/uploads -v "%cd%/backups:/backups" alpine tar -czf /backups/uploads_$(date +%Y%m%d_%H%M%S).tar.gz -C /uploads .
```

PowerShell timestamp variant:

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
docker run --rm -v telegramshopplatform_uploads_data:/uploads -v "${PWD}/backups:/backups" alpine tar -czf "/backups/uploads_$stamp.tar.gz" -C /uploads .
```

## Uploads Restore

Restore uploads into the production uploads volume:

```bash
docker run --rm -v telegramshopplatform_uploads_data:/uploads -v "$(pwd)/backups:/backups" alpine sh -c "rm -rf /uploads/* && tar -xzf /backups/uploads_YYYYMMDD_HHMMSS.tar.gz -C /uploads"
```

On Windows PowerShell:

```powershell
docker run --rm -v telegramshopplatform_uploads_data:/uploads -v "${PWD}/backups:/backups" alpine sh -c "rm -rf /uploads/* && tar -xzf /backups/uploads_YYYYMMDD_HHMMSS.tar.gz -C /uploads"
```

## Backup Schedule

- PostgreSQL: at least daily for MVP, more often before launches or data imports.
- Uploads: daily, and immediately before storage migrations.
- Keep at least one recent restore-tested backup outside the deployment host.
- Do not store backups in git.
