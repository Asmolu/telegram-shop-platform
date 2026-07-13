# Rollback

Preferred strategy: no-downgrade-first. Stop/revert application rollout to known compatible image
while retaining additive schema. Verify current/head, logs and critical paths.

Schema downgrade is destructive for `0056` notification history and `0055` Look badges. Before any
downgrade: verified backup, data-loss analysis, explicit approval, maintenance window and restore plan.
Do not recreate PostgreSQL/Redis volumes during ordinary app rollback.

Rollback trigger/owner/SLA are `NOT APPROVED`. Canonical deploy context:
[../PRODUCTION_DEPLOYMENT.md](../PRODUCTION_DEPLOYMENT.md).

