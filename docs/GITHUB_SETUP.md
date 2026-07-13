# GitHub workflow

**Назначение:** безопасная работа с репозиторием StyleXac; production credentials сюда не входят.

Основная ветка — `main`; для Codex-веток используется префикс `codex/`, если владелец не задал иной. Каждый PR имеет краткий scope, связанные issue/decision, риски, migration/env/docs impact, выполненные проверки и rollback/forward-fix note. Секреты, env, uploads, dumps и персональные данные не прикладываются.

Перед публикацией проверить `git status --short`, `git diff --check`, релевантные tests/builds, migration head и documentation links. Schema, auth, payments, RBAC, notifications, uploads и infrastructure требуют усиленного review. Merge в `main` не является автоматическим разрешением на production deployment.

Branch protection рекомендуется настроить с required reviews/checks, запретом force push, secret/dependency scanning и ограниченными release permissions. Commit/push/PR выполняются только по явному запросу владельца. Процесс релиза — [Release Process](engineering/RELEASE_PROCESS.md), contributing — [Contributing](engineering/CONTRIBUTING.md).
