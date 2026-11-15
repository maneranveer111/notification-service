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

---

## Production with HTTPS

For public-facing production deployments, use `docker-compose.prod.yml`. This configuration includes automatic HTTPS with Caddy, Redis password authentication, resource limits, healthchecks, and strict production security validation.

### Server Requirements
- Linux host (Ubuntu 22.04+ or Debian 12 recommended)
- 2 CPU cores, 2 GB RAM minimum (4 GB recommended for heavier workloads)
- Docker Engine 24+ and Docker Compose v2+
- Public IP address with ports 80 and 443 open

### 1. DNS & Firewall Configuration
1. Create a DNS A/AAAA record pointing your domain (e.g. `notify.example.com`) to your server's public IP address.
2. Allow incoming traffic on ports 80 (HTTP) and 443 (HTTPS) in your firewall (e.g., `ufw allow 80/tcp && ufw allow 443/tcp`).

### 2. Generate Production Environment
Run the setup generator with your domain name:

```bash
python scripts/generate_env.py --production --domain notify.example.com
```

This generates `.env` with strong random secrets (JWT secret, Redis password, Fernet encryption key, API key, etc.) and pre-configures domain URLs.

> **CRITICAL WARNING — Back Up Your ENCRYPTION_KEY**:
> The `ENCRYPTION_KEY` in `.env` is used to encrypt per-workspace credentials (e.g. SMTP passwords, API keys) at rest in the database. If this key is lost, all encrypted credentials become permanently unrecoverable. Store a copy of `ENCRYPTION_KEY` in a secure password manager or offline vault immediately.

### 3. Deploy Containers
Build and launch the full production stack:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Caddy will automatically provision and renew a TLS certificate via Let's Encrypt or ZeroSSL.

### 4. Create the First Admin Account
Open `https://<your-domain>` in your browser. Complete the initial setup screen to register the superadmin account. Once created, signups default to `invite_only`.

### 5. What ENVIRONMENT=production Enforces
When `ENVIRONMENT=production`, the application refuses to start if security prerequisites are not met:
- `JWT_SECRET` must be set and at least 32 characters long.
- `ENCRYPTION_KEY` must be set and contain valid 32-byte Fernet key(s).
- `API_KEY` must be set, at least 24 characters, and cannot be a common placeholder.
- `UNSUBSCRIBE_SECRET` must be set.
- `SYSTEM_MAIL_BACKEND` cannot be `console` (must use real email `provider`).
- `PUBLIC_BASE_URL` and `FRONTEND_PUBLIC_URL` must use `https://` (unless host is localhost).
- `SIGNUP_MODE` must be `open`, `invite_only`, or `closed`.

### 6. Backups & Restore
Use the automated POSIX shell scripts in `scripts/`:

**Create a backup:**
```bash
./scripts/backup.sh
```
This dumps the database and saves a gzipped timestamped file into `backups/`, keeping the newest 14 backups.

**Automate via Cron:**
Run `crontab -e` and add a daily job at 03:00 UTC:
```cron
0 3 * * * cd /opt/notification-service && ./scripts/backup.sh >> /var/log/notification-backup.log 2>&1
```
*Always copy backups off-server (e.g. S3, rsync) for disaster recovery.*

**Restore from a backup:**
```bash
./scripts/restore.sh backups/notifications-YYYY-MM-DD-HHMM.sql.gz
```
The script safely prompts for confirmation, stops API/worker processes, recreates a clean database, restores the data, and restarts services.

### 7. Viewing Logs
View real-time structured JSON container logs:

```bash
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f worker
docker compose -f docker-compose.prod.yml logs -f caddy
```

### 8. Updating in Production
To update to a newer release:

```bash
# Pull latest code or images
git pull
docker compose -f docker-compose.prod.yml pull
# Apply updates with automatic migration
docker compose -f docker-compose.prod.yml up -d --build
```

