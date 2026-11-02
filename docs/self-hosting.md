# Self-Hosting Guide

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 24 or later
- [Docker Compose](https://docs.docker.com/compose/) v2 or later (bundled with Docker Desktop)
- Git

## Quick Start

**1. Clone the repository**

```bash
git clone https://github.com/your-org/notification-service.git
cd notification-service
```

**2. Generate secrets**

```bash
python scripts/generate_env.py
```

This creates a `.env` file with random secrets for all sensitive fields.

**3. Review and edit `.env`**

Open `.env` and fill in any provider credentials you want to use (Brevo, Twilio, SMTP). The service starts without them — you can also add credentials per-workspace in the dashboard.

**4. Start all services**

```bash
docker compose up -d
```

**5. Open the dashboard**

Visit [http://localhost](http://localhost). On first launch, register an account — the first registered user becomes the superadmin.

## Service Descriptions

| Service | Image | Purpose |
|---|---|---|
| `db` | `postgres:16` | Primary PostgreSQL database |
| `redis` | `redis:7-alpine` | Message broker and result backend for Celery |
| `migrate` | `./backend` | Runs `alembic upgrade head` on startup, then exits |
| `api` | `./backend` | FastAPI application serving the REST API |
| `worker` | `./backend` | Celery worker that processes notification tasks |
| `web` | `./frontend` | Nginx serving the React SPA and proxying `/api/` to the API |

## Running Migrations Manually

If you need to run migrations outside the normal startup flow:

```bash
docker compose run --rm migrate
```

Or against a running container:

```bash
docker compose exec api alembic upgrade head
```

## Enabling the Scheduler

The Celery beat scheduler handles periodic tasks (e.g., scheduled notifications). It is disabled by default to avoid conflicts when running multiple worker containers.

To enable it, set `ENABLE_BEAT=true` on the `worker` service in your `.env` or `docker-compose.override.yml`:

```yaml
# docker-compose.override.yml
services:
  worker:
    environment:
      ENABLE_BEAT: "true"
```

Only one worker instance should have beat enabled at a time.

## Backup and Restore

**Backup the database:**

```bash
docker compose exec db pg_dump -U postgres notification_db > backup.sql
```

**Restore from a backup:**

```bash
docker compose exec -T db psql -U postgres notification_db < backup.sql
```

**Back up the named volume directly:**

```bash
docker run --rm -v notification-service_pgdata:/data -v $(pwd):/backup \
  alpine tar czf /backup/pgdata-backup.tar.gz -C /data .
```

## Upgrading

Pull the latest images and restart services:

```bash
docker compose pull
docker compose up -d
```

Migrations run automatically via the `migrate` service on each startup. Review the changelog before upgrading across major versions.
