# Telegram Shop Platform

Telegram Shop Platform is a modular e-commerce system for a clothing shop built around a Telegram Mini App and a Seller Panel.

The repository is intentionally prepared as a **Python/FastAPI modular monolith** backend with separate frontend applications.

## Current status

This is a project scaffold and architecture baseline, not a completed product. The repository is prepared for iterative development with Codex through Git.

## Stack

| Layer          | Technology                          |
| -------------- | ----------------------------------- |
| Customer app   | React + Vite + TypeScript           |
| Seller panel   | React + Vite + TypeScript           |
| Backend API    | Python 3.12 + FastAPI               |
| ORM            | SQLAlchemy 2.0 async                |
| Migrations     | Alembic                             |
| Database       | PostgreSQL                          |
| Cache / queues | Redis                               |
| Files          | Local `/uploads`, cloud-ready later |
| API contract   | OpenAPI                             |
| Auth           | Telegram initData validation + JWT  |

## Repository structure

```text
.
├── backend/              # FastAPI backend
├── mini-app/             # Telegram Mini App frontend
├── seller-panel/         # Seller/Admin frontend
├── docs/                 # Development documentation
├── .github/              # GitHub workflows and templates
├── AGENTS.md             # Instructions for Codex / AI coding agents
├── SRS.README.md         # Software Requirements Specification
├── SPRINT_PLAN.md        # Sprint-based implementation plan
└── docker-compose.yml    # Local dev infrastructure
```

## Backend architecture

```text
backend/app/
├── api/                  # API router composition
├── common/               # shared dependencies and helpers
├── core/                 # config, security, exception handling
├── db/                   # SQLAlchemy base, session, models
├── events/               # event names / event contract
├── jobs/                 # background job placeholders
└── modules/              # feature modules
    ├── auth/
    ├── users/
    ├── products/
    ├── categories/
    ├── tags/
    ├── banners/
    ├── promo_codes/
    ├── cart/
    ├── orders/
    ├── reviews/
    ├── favorites/
    ├── notifications/
    ├── uploads/
    ├── telegram/
    └── statistics/
```

## Local start with Docker

Create a local backend env file:

```bash
cp backend/.env.example backend/.env
```

Start services:

```bash
docker compose up -d --build
```

Apply migrations:

```bash
docker compose exec backend alembic upgrade head
```

Check backend health:

```bash
curl http://localhost:8000/health
```

Open API docs:

```text
http://localhost:8000/docs
http://localhost:8000/api/v1/openapi.json
```

## Local backend without Docker

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

For Linux/macOS:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend development

Mini App:

```bash
cd mini-app
npm install
npm run dev
```

Seller Panel:

```bash
cd seller-panel
npm install
npm run dev
```

## Quality checks

Backend:

```bash
cd backend
ruff check .
pytest
python -m compileall app tests
```

Frontend:

```bash
cd mini-app
npm run build

cd ../seller-panel
npm run build
```

## Important rules

- Do not reintroduce NestJS or Prisma into the backend.
- SQLAlchemy models and Alembic migrations are the database source of truth.
- Routers must stay thin; business logic belongs in services.
- Repositories own database queries.
- Telegram is a UI/transport layer, not the source of system data.
- Order data must be persisted in PostgreSQL before notifications are emitted.
- Never commit `.env`, tokens, private keys, uploaded user files, or database dumps.

See `AGENTS.md` before giving tasks to Codex.

## Project Documentation

- `SRS.README.md` — product/system requirements.
- `SPRINT_PLAN.md` — implementation roadmap.
- `AGENTS.md` — Codex/agent development rules.
- `UI_DESIGN_SPEC.README.md` — Mini App and Seller Portal UI specification.
