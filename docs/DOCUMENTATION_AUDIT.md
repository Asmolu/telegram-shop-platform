# Аудит существующей документации

Статус: audit record. Дата: 2026-07-13. Конфиденциальность: Internal.

Code, migrations, tests и подтвержденный release snapshot имеют приоритет над Markdown.
Ни один historical ADR не удален.

| Original file / group | Status | Problem | Action / replacement | Broken-link risk |
| --- | --- | --- | --- | --- |
| `README.md` | Updated | stale head, incomplete sales/legal posture | rewritten as entry point | Low |
| `docs/PROJECT_HANDOVER.md` | Updated | stale heads and duplicated rules | autonomous handover | Low |
| `docs/ARCHITECTURE.md` | Compatibility | duplicated engineering facts | points to `engineering/ARCHITECTURE.md` | Low |
| `docs/ENVIRONMENT.md` | Compatibility | incomplete current variables | `engineering/CONFIGURATION.md` | Low |
| `docs/PRODUCTION_DEPLOYMENT.md` | Updated | stale migration commands/head | remains canonical deployment file | Low |
| `docs/OPERATIONS.md` | Compatibility | mixed runbooks | `operations/OPERATIONS_RUNBOOK.md` | Low |
| `docs/BACKUP_AND_RESTORE.md` | Compatibility | split/duplicated backup rules | `operations/BACKUP_AND_RESTORE.md` | Low |
| `docs/BACKUP_STRATEGY.md` | Compatibility | stale heads, policy duplication | same canonical backup doc | Low |
| `docs/CUSTOMER_NOTIFICATIONS_ARCHITECTURE.md` | Compatibility | no full current matrix in one source | `product/NOTIFICATIONS.md` and engineering docs | Low |
| `docs/TELEGRAM_CHANNEL_ENTRY.md` | Compatibility | narrow topic | `engineering/TELEGRAM_INTEGRATION.md` | Low |
| `docs/TESTING.md` | Updated | stale head/counts | canonical testing snapshot | Low |
| `docs/LOCAL_DEVELOPMENT.md` | Updated | stale grep/head | canonical local guide | Low |
| `docs/SECURITY_REVIEW.md` | Compatibility | review notes, not threat model | `security/*` | Low |
| `docs/FRANKFURT_DEPLOYMENT_READINESS.md` | Deprecated | point-in-time readiness and stale head | `PRODUCTION_STATE.md` | Medium |
| `docs/ANALYTICS_TELEMETRY.md` | Current with canonical links | useful focused topic | retained; feature status in catalog | Low |
| `docs/CODEX_WORKFLOW.md` | Current | agent workflow, not product truth | retained; `AGENTS.md` authoritative | Low |
| `docs/GITHUB_SETUP.md` | Current | contributor-specific | retained; engineering contributing links | Low |
| Root `CHANGELOG.md` | Historical | not complete 2026-07-13 release | canonical `docs/CHANGELOG.md` | Medium |
| `CONTRIBUTING.md`, `SECURITY.md` | Current entry points | concise, English | canonical engineering/security docs added | Low |
| `SRS.README.md`, `SPRINT_PLAN.md` | Historical scope | not production source of truth | classified Internal historical | Medium |
| `UI_DESIGN_SPEC.README.md` | Current UI authority | only UI scope | retained by AGENTS rule | Low |
| component READMEs | Current entry points | incomplete cross-domain context | retained and linked from docs index | Low |
| `.agents/*.md` | Working note | not product documentation | excluded from current truth | None |
| `.codex-tmp/**/*.md` | Temporary tracked snapshot | obsolete copy | explicitly excluded; not linked | None |

Deprecated content was not moved because filenames are externally referenced. Compatibility notices
preserve links while directing readers to canonical replacements.

