# Database operations

Use Compose one-off backend with production env for Alembic. Always check `alembic heads` and
`alembic current` before upgrade; expected head is `20260713_0056`. Run backup before schema change.

Checkout/restock/outbox rely on PostgreSQL row locks and PostgreSQL-specific SQL. SQLite is not a
production substitute. Never edit data ad hoc without incident/change record, transaction boundary,
backup and verification query. Database dumps contain PII and are Restricted.

Routine maintenance (vacuum, index health, capacity, retention) schedule is
**NEEDS VERIFICATION** from DBA/operations owner; blocks scale readiness claims.

