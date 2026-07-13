# Backend architecture

Runtime: Python 3.12+, FastAPI/Uvicorn, async SQLAlchemy. `app.main:create_app` mounts API under
`/api/v1`, static uploads and middleware for CORS, rate limiting, request IDs/logging and errors.

Module contract:

```text
backend/app/modules/<feature>/
├── router.py      HTTP parsing/dependencies/response
├── schemas.py     Pydantic contract
├── service.py     rules/transactions
└── repository.py  SQLAlchemy queries
```

Lifespan starts campaign, manual-payment expiration and outbox workers according to config.
Business logic must not move into routers. SQLAlchemy models currently remain centralized in
`backend/app/db/models.py`.

Source: `backend/app/main.py`, `backend/app/api/router.py`, `AGENTS.md`.

