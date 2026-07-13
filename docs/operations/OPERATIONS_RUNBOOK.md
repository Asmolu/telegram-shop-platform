# Operations runbook

All commands run only by authorized operator on production host. This audit did not run them.

| Check | Command/observation | Escalate when |
| --- | --- | --- |
| Containers | `docker compose --env-file backend/.env.production -f docker-compose.prod.yml ps` | unhealthy/restarting |
| Backend logs | same prefix + `logs --tail=250 backend` | exceptions/outbox backlog |
| Frontend logs | `logs --tail=120 mini-app seller-panel` | startup/build serving errors |
| API health | `curl -fsS https://api.stylexac.ru/health` | non-200/wrong body |
| Public surfaces | `curl -I` each current domain | non-200/TLS/redirect anomaly |
| Backup | systemd status/journal | local/restore not passed or remote unexpected |
| Outbox | ADMIN diagnostics API | old pending, processing lock or FAILED |
| Disk | host/volume capacity checks | uploads/DB/backups near threshold |

Do not print environment file. Record timestamps, commit, migration, request IDs and sanitized errors.
Canonical deployment/backup/incident procedures are linked from [../README.md](../README.md).

