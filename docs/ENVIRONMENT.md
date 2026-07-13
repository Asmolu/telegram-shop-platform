# Окружение и конфигурация

**Срез:** `325e3af`, 13 июля 2026 года. Канонический каталог переменных — [Configuration](engineering/CONFIGURATION.md).

Локальная разработка использует repository examples и локальную `.env`; production использует `backend/.env.production` на host. Реальные env-файлы, tokens, passwords, URLs с credentials и private keys не читаются в документацию и не коммитятся. Frontend получает API base через Vite variables, production URL не hardcode.

Основные группы настроек: PostgreSQL/Redis, JWT/auth, Telegram Bot 1/Bot 2, Mini App freshness, uploads/storage, CORS/domains, rate limiting, notification/campaign workers, telemetry, backup и frontend build. Имена и defaults сверяются с settings code, compose и examples; production значения проверяются только на наличие/валидность без печати.

Известный drift: env examples не отражают шесть текущих campaign worker variables и две campaign rate-limit variables; Mini App example содержит telemetry variables отдельно. До релиза examples следует синхронизировать либо зафиксировать осознанное исключение. Production контекст — [Production Deployment](PRODUCTION_DEPLOYMENT.md).
