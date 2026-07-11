# Transactional outbox working notes

## Architecture audit summary

- Orders currently collect `ORDER_CREATED`, `PROMO_USED`, `ORDER_STATUS_CHANGED`, and
  `ORDER_SHIPPED` in memory, commit the business transaction, then invoke an in-process
  publisher. A process exit between commit and publish loses the event.
- The order publisher fans out sequentially to seller `Notification` creation/delivery and
  customer `CustomerServiceNotificationDelivery` creation/delivery. Those tables only help
  after their rows exist and neither currently has a durable source-event key.
- Manual payment submitted/approved/rejected/expired events use the same post-commit pattern.
- Return creation sends directly after commit and is not event-driven. This task will not
  alter return business rules or message formatting; the remaining gap will be documented.
- Analytics is intentionally best-effort post-commit telemetry and remains outside the
  domain-event outbox so its existing semantics and checkout latency behavior do not change.
- Existing long-running jobs run as cleanly stoppable FastAPI lifespan tasks. The outbox
  worker will follow that convention and use short database transactions around claims and
  acknowledgements, never around Telegram calls.

## Implementation plan

1. Add PostgreSQL-backed `OutboxEvent` and per-consumer `OutboxDelivery` models plus revision
   `20260711_0053`, with unique event UUIDs, polling/locking indexes, bounded attempts, and
   durable consumer idempotency constraints on existing notification records.
2. Add an outbox module with JSON-safe atomic enqueue, `FOR UPDATE SKIP LOCKED` batch claims,
   stale-lock recovery, independent seller/customer dispatch, bounded exponential retry,
   sanitized errors, status aggregation, diagnostics, and controlled failed-event retry.
3. Replace order and manual-payment post-commit publisher calls with same-transaction enqueue.
   Keep current payload builders and publisher formatting/delivery code as dispatch targets.
4. Start the worker from FastAPI lifespan using production-safe settings. Add an authorized
   read-only diagnostics and retry API without exposing payloads.
5. Add unit/integration/PostgreSQL concurrency and migration tests, update operational and
   deployment documentation, then run the required backend and repository checks.
