# Production deployment (navigation copy)

Canonical operational procedure: [../PRODUCTION_DEPLOYMENT.md](../PRODUCTION_DEPLOYMENT.md).
Production path is `/opt/telegram-shop`; never use the stale path in repository systemd template.

Minimum gates: authorized operator, clean tracked worktree, exact commit, verified backup, Compose
config, Alembic heads/current, build, upgrade, recreate app services, health/log/manual smoke and
release record. This document contains no credentials.

