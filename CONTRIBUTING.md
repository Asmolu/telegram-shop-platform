# Contributing

## Development workflow

1. Create a feature branch from `main`.
2. Make a focused change.
3. Run relevant checks.
4. Update documentation if behavior, commands, architecture, or environment variables changed.
5. Open a pull request.

## Branch naming

Use short descriptive names:

```text
feature/product-catalog
feature/order-checkout
fix/auth-validation
chore/github-ci
```

## Commit messages

Use imperative style:

```text
Add product catalog models
Implement checkout transaction
Fix upload path validation
```

## Backend conventions

- FastAPI routers must stay thin.
- Services contain business logic.
- Repositories contain database queries.
- Pydantic schemas define API DTOs.
- SQLAlchemy models + Alembic migrations define schema changes.
- Do not add Prisma or NestJS.

## Checks

Backend:

```bash
cd backend
python -m compileall app tests
ruff check .
pytest
```

Frontend:

```bash
cd mini-app
npm run build

cd ../seller-panel
npm run build
```
