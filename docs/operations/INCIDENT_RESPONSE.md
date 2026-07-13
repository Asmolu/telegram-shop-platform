# Incident response

1. **Declare** severity, incident commander, start time and affected surfaces.
2. **Contain** writes/rollout/credentials without destroying evidence.
3. **Observe** container state, health, recent logs, DB/Redis, outbox and backup status.
4. **Decide** rollback, roll-forward, credential rotation or restore.
5. **Recover** with two-person review for data/secret operations where possible.
6. **Verify** customer and seller critical paths; record exact commit/migration/archive.
7. **Communicate** factual status without exposing PII/secrets or promising unapproved ETA.
8. **Review** root cause, timeline, impact, corrective actions and documentation changes.

Severity/notification deadlines and incident owner are **NEEDS BUSINESS DECISION**. Legal owner must
define personal-data incident notification obligations; blocks legal launch readiness.

