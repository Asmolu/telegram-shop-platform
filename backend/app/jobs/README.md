# Jobs

Background jobs should be introduced after the synchronous MVP flow is stable.

Recommended path:

1. Keep critical business transactions synchronous.
2. Emit events after DB commit.
3. Use Redis-backed jobs for notifications and analytics enrichment.
4. Keep job handlers idempotent.
