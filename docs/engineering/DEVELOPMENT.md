# Development

Prerequisites: Git, Python 3.12+, Docker Compose, PostgreSQL 16/Redis 7 when native, Node.js/npm.
**NEEDS VERIFICATION**: exact supported Node.js LTS is not pinned in package manifests; engineering
owner must approve it. This blocks perfectly reproducible onboarding, not current builds.

Windows:

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m alembic upgrade head
uvicorn app.main:app --reload
```

Linux uses `python3.12 -m venv .venv` and `source .venv/bin/activate`. Frontends: `npm install`,
then `npm run dev` in each directory. Ports: backend 8000, Mini App 5173, Seller Panel 5174.

`.env` is local. `.env.production` is VDS/server and production-domain checks only. Never copy
production values into local examples/docs.

Migrations: create Alembic revision, review upgrade/downgrade and chain, run migration tests and
`alembic check`. Runtime architecture rules remain in `AGENTS.md`.

