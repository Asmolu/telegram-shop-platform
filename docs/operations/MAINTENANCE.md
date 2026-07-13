# Maintenance

| Cadence | Work | Evidence |
| --- | --- | --- |
| Daily | health, container state, backup local/restore/remote status, FAILED outbox | journal/API record |
| Weekly | disk/uploads/DB growth, campaign failures, dependency/security alerts | maintenance record |
| Release | backup, build/migrate/smoke, changelog | release record |
| Periodic | restore exercise, secret/access review, retention cleanup, dependency updates | approved schedule |

Exact periodic cadence except coded backup schedule is `NOT APPROVED`. Upload orphan cleanup is not
documented as a comprehensive worker; do not delete files based only on filesystem listing.

