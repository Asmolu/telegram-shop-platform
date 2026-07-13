# Известные ограничения и readiness gaps

Статус: канонический register. Последняя проверка: 2026-07-13. Конфиденциальность: Internal.

Severity: Critical, High, Medium, Low. Probability — качественная оценка по repository evidence,
не статистическая вероятность.

| ID | Area | Issue / evidence | Impact | Severity / probability | Sales blocker | Launch blocker | Workaround / required action | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-01 | Legal | 24-hour window в `returns/service.py`; legal opinion отсутствует | consumer-law risk | Critical / High | Yes | Yes | lawyer review; согласовать policy и code change отдельно | Business + Legal | Open |
| R-02 | Privacy | retention/export/deletion policy не реализована end-to-end | personal-data risk | Critical / High | Yes | Yes | утвердить policy, DSAR process, deletion/export scope | Legal + Product | Open |
| R-03 | Payments | только manual SBP; provider/receipts отсутствуют | ручной труд, fiscal risk | High / High | Yes | Conditional | утвердить модель или provider project | Business | Open |
| R-04 | Tenancy | модели не имеют tenant boundary | нельзя обещать multi-tenant SaaS | High / High | Yes | Yes для shared SaaS | отдельные deployments или tenant redesign | Architecture | Open |
| R-05 | Availability | single-server Compose topology | single point of failure | High / Medium | Yes | Conditional | failover design, monitoring, tested DR | Operations | Open |
| R-06 | Backup | remote upload cadence 7 и может быть skipped/failed | offsite gap | High / Medium | Yes | Conditional | daily review, alert, approved offsite policy | Operations | Open |
| R-07 | DR | RPO/RTO `NOT APPROVED` | нельзя обещать recovery target | High / High | Yes | Yes для SLA | business decision и restore exercise | Business + Ops | Open |
| R-08 | Operations | systemd template path не совпадает с production path | reinstall failure | High / Medium | No | Yes при переустановке | исправить unit отдельной ops change; verify host unit | Operations | Open |
| R-09 | Monitoring | optional Sentry; centralized metrics/alerts не подтверждены | позднее обнаружение incident | High / Medium | Yes | Conditional | monitoring acceptance criteria | Operations | Open |
| R-10 | Support | owner, hours, escalation и SLA не утверждены | support ambiguity | High / High | Yes | Yes | назначить owner/tier/escalation | Business | Open |
| R-11 | Looks | backend/UI выбирают все components; stored defaults не управляют initial selection | claim mismatch | Medium / High | No | No | demo wording; решить product behavior | Product | Partial |
| R-12 | `ONE_SIZE` | semantic «accessories only» не enforced by category | catalog quality risk | Medium / Medium | No | No | seller onboarding validation | Product | Open |
| R-13 | Order status | seller/admin API допускает non-linear movement/re-entry | correction useful, audit complexity | Medium / Medium | No | No | permissions, audit review, SOP | Product | Accepted |
| R-14 | Files | local volume, lifecycle cleanup/capacity alert не подтверждены | storage growth | Medium / High | No | Conditional | quota, cleanup, capacity alert | Operations | Open |
| R-15 | Inventory | нет external ERP synchronization/import pipeline | manual catalog/stock | Medium / High | Yes for large sellers | Conditional | scoped import/custom integration | Product | Open |
| R-16 | Analytics | event store exists; BI governance/retention ownership limited | reporting limits | Medium / Medium | No | No | define KPIs and access | Product | Partial |
| R-17 | Telegram | platform, private-chat and WebView constraints | delivery/UX dependency | Medium / High | No | No | disclose, browser fallback tests | Product | Accepted |
| R-18 | Bot messaging | channel entry не создает Bot 1 private chat | campaigns unavailable until `/start` | Medium / High | No | No | write access for service; `/start` for campaigns | Support | Accepted |
| R-19 | Configuration | sample env misses campaign settings | deployment drift | Medium / Medium | No | Conditional | align sample in separate config change | Engineering | Open |
| R-20 | Security | secret rotation/access ownership not documented as executed | credential risk | High / Medium | Yes | Conditional | access register and rotation schedule | Security | Open |
| R-21 | Audit | critical actions covered selectively; completeness not certified | due diligence gap | Medium / Medium | Yes | No | action-by-action audit coverage test | Security | Open |
| R-22 | Redis | used for cache/rate limit; critical recovery dependency not defined | fail-open/fallback ambiguity | Medium / Low | No | No | document/cache drills; PostgreSQL remains truth | Operations | Open |

Источник: `backend/app/db/models.py`, `backend/app/modules/returns/service.py`,
`backend/app/modules/looks/service.py`, `backend/app/core/config.py`,
`backend/scripts/backup_production.py`, `docker-compose.prod.yml`,
`scripts/systemd/telegram-shop-backup.service`.

