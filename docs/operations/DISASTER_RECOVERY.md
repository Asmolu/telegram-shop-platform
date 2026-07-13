# Disaster recovery

## Scenarios

| Scenario | First containment | Recovery source | Critical verification |
| --- | --- | --- | --- |
| Backend image failure | stop rollout, keep DB/Redis | previous code/image | health + migrations compatible |
| DB corruption/loss | isolate writes | verified PostgreSQL backup | schema/current + domain smoke |
| Upload loss | stop destructive writes | uploads archive | media paths resolve |
| Host loss | acquire replacement host | repo + local/offsite backup | domains/TLS/webhooks/secrets |
| Credential compromise | revoke/rotate | secret inventory | bots/JWT/DB/Yandex/Sentry |
| Telegram outage | preserve queued state | no local fix | retry/backoff/customer notice |

Single-server topology means host loss affects all application services. Remote backup is conditional;
an operator must identify latest verified local and offsite archive before promising recovery.

RPO/RTO are `NOT APPROVED`. A full restore/cutover exercise on a separate host is
**NEEDS VERIFICATION**; operations owner must provide dated evidence. Blocks contractual DR claims.

