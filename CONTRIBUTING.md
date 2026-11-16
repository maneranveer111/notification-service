# Contributing

Thanks for your interest in contributing to Notification Service.

## Development Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
cp .env.example .env       # edit with local DB/Redis credentials
alembic upgrade head

# API server
uvicorn app.main:app --reload --port 8001

# Celery worker (separate terminal)
celery -A app.celery_app worker --loglevel=info -Q notification_service_queue --pool=solo
```

### Frontend

```bash
cd frontend
npm ci
cp .env.example .env       # set VITE_API_BASE_URL=http://localhost:8001
npm run dev
```

## Running Tests

```bash
cd backend && pytest -q
```

Tests require a running PostgreSQL on `localhost:5432` and Redis on `localhost:6379`. Use the connection strings in `backend/.env.example` as a guide.

## Running the Linter

```bash
cd frontend && npm run lint
```

## Commit Style

This project uses [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Use for |
|---|---|
| `feat:` | New features |
| `fix:` | Bug fixes |
| `docs:` | Documentation only |
| `chore:` | Maintenance, dependency bumps |
| `refactor:` | Code changes with no behaviour change |
| `test:` | Adding or updating tests |

Example: `feat(notifications): add webhook channel support`

## Pull Request Process

1. Fork the repository and create a branch from `main`.
2. Make your changes and add tests that cover the new behaviour.
3. Ensure all tests pass (`cd backend && pytest -q`) and the frontend builds (`cd frontend && npm run build`).
4. Open a pull request against `main`. Fill in the PR template.
5. A maintainer will review and merge. Expect feedback within a few days.

## Code of Conduct

Be respectful. Harassment, discrimination, and personal attacks are not tolerated. Treat every contributor as you would want to be treated.
