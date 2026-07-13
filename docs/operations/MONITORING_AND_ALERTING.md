# Monitoring and alerting

Implemented evidence: container healthcheck, `/health`, structured request logging/request IDs,
optional Sentry, outbox diagnostics, backup Telegram reports and telemetry/analytics tables.

Not confirmed as production controls: centralized logs, external uptime probe, metrics/graphs,
disk/DB capacity alerts, outbox/worker alerts, on-call routing and SLO dashboard.

| Signal | Desired alert | Owner/status |
| --- | --- | --- |
| public/API health | consecutive failures | Operations — NEEDS VERIFICATION |
| backend restart/5xx | threshold + request ids | Operations — NEEDS VERIFICATION |
| outbox FAILED/oldest pending | count/age threshold | Engineering — threshold NOT APPROVED |
| backup local/restore | any failure | Operations — journal/report review implemented |
| remote backup | overdue/failed | Operations — cadence exists, alert NEEDS VERIFICATION |
| disk/DB/uploads | capacity threshold | Operations — NOT APPROVED |
| Telegram 403/429 | blocked/rate-limit trend | Support/Engineering — logs available |

This blocks SLA/observability maturity claims.

