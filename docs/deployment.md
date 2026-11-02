# Deployment Guide

## Environment Variables Reference

| Env Var | Default | Description |
|---|---|---|
| `APP_NAME` | `Notification Service` | Application name shown in the UI |
| `DEBUG` | `false` | Enable debug mode (never true in production) |
| `DATABASE_URL` | — | PostgreSQL connection string (required) |
| `REDIS_URL` | `redis://localhost:6379` | Redis URL; used for Celery broker and result backend |
| `DB_POOL_SIZE` | `5` | SQLAlchemy connection pool size per process |
| `DB_MAX_OVERFLOW` | `5` | Extra connections allowed above pool size |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait before raising pool timeout |
| `DB_POOL_RECYCLE` | `1800` | Recycle connections older than this many seconds |
| `CELERY_QUEUE` | `notification_service_queue` | Celery queue name |
| `PUBLIC_BASE_URL` | `http://localhost:8001` | Public API URL used in webhook status callbacks |
| `WEBHOOK_SECRET` | — | HMAC secret for signing outgoing webhook payloads |
| `WEBHOOK_VERIFY` | `true` | Verify TLS certificates when delivering webhooks |
| `EMAIL_PROVIDER_ORDER` | `brevo,smtp` | Comma-separated provider preference (platform-level) |
| `SMTP_HOST` | — | SMTP server hostname |
| `SMTP_USER` | — | SMTP authentication username |
| `SMTP_PASSWORD` | — | SMTP authentication password |
| `SMTP_FROM_EMAIL` | — | Default sender address for SMTP |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USE_TLS` | `true` | Enable STARTTLS |
| `BREVO_API_KEY` | — | Brevo (Sendinblue) transactional email API key |
| `BREVO_FROM_EMAIL` | — | Default sender address for Brevo |
| `TWILIO_ACCOUNT_SID` | — | Twilio account SID for SMS |
| `TWILIO_AUTH_TOKEN` | — | Twilio auth token |
| `TWILIO_FROM_NUMBER` | — | Twilio sender phone number |
| `API_KEY` | — | Master API key for the default workspace (required) |
| `JWT_SECRET` | — | Secret for signing JWT tokens (required) |
| `JWT_EXPIRE_MINUTES` | `480` | JWT token lifetime in minutes |
| `METRICS_TOKEN` | — | Bearer token protecting the `/metrics` endpoint |
| `LOG_FORMAT` | `text` | Log format: `text` or `json` |
| `FRONTEND_URL` | `http://localhost:5173` | Allowed CORS origins (comma-separated) |
| `SCHEDULE_MAX_DAYS` | `30` | Max days ahead a notification can be scheduled |
| `BULK_MAX_RECIPIENTS` | `200` | Max recipients per bulk send request |
| `MAX_WORKSPACES_PER_USER` | `5` | Max workspaces one user can own |
| `UNSUBSCRIBE_SECRET` | — | HMAC secret for one-click unsubscribe links |
| `WEBHOOK_CHANNEL_ALLOWED_HOSTS` | `hooks.slack.com,discord.com,discordapp.com` | Allowed hosts for webhook channel delivery |
| `SIGNUP_MODE` | `open` | `open`, `invite_only`, or `closed` |
| `REQUIRE_EMAIL_VERIFICATION` | `true` | Require email confirmation on signup |
| `SYSTEM_MAIL_BACKEND` | `provider` | `provider` (real email) or `console` (log only) |
| `FRONTEND_PUBLIC_URL` | `http://localhost:5173` | Public frontend URL used in system emails |
| `ENCRYPTION_KEY` | — | Fernet key(s) for encrypting per-workspace provider credentials |
| `ALLOW_PRIVATE_SMTP_HOSTS` | `false` | Allow outbound SMTP to private/internal hosts |
| `TRUSTED_PROXY_COUNT` | `0` | Number of trusted reverse proxies for real-IP detection |
| `RATE_LIMIT_STORAGE_URI` | — | Explicit Redis URI for rate limit counters |
| `QUOTA_ENABLED` | `true` | Enable per-workspace sending quotas |
| `TURNSTILE_SECRET_KEY` | — | Cloudflare Turnstile secret key (CAPTCHA) |
| `TURNSTILE_SITE_KEY` | — | Cloudflare Turnstile site key (CAPTCHA) |

## Scaling API Workers

**Option 1 — Uvicorn workers (single container):**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Option 2 — Multiple container replicas (docker-compose.override.yml):**

```yaml
services:
  api:
    deploy:
      replicas: 3
```

Place a load balancer (e.g., nginx, Traefik) in front of the replicas. Set `TRUSTED_PROXY_COUNT` to match your proxy depth so rate limiting uses the real client IP.

## Scaling Celery Workers

Run additional worker containers — they all consume from the same Redis queue:

```bash
docker compose up -d --scale worker=3
```

Only one worker should have `ENABLE_BEAT=true` to avoid duplicate scheduled task submissions.

## External Managed PostgreSQL

Change `DATABASE_URL` in `.env` to point at your managed instance:

```
DATABASE_URL=postgresql://user:password@your-db-host:5432/notification_db
```

Remove (or override) the `db` service from `docker-compose.yml`. Run migrations on first deploy:

```bash
docker compose run --rm migrate
```

## External Managed Redis

Change `REDIS_URL` in `.env`:

```
REDIS_URL=redis://:your-password@your-redis-host:6379/0
```

Remove (or override) the `redis` service from `docker-compose.yml`.

## Reverse Proxy

Example nginx config for SSL termination (Certbot or Cloudflare):

```nginx
server {
    listen 443 ssl;
    server_name notifications.example.com;

    ssl_certificate     /etc/letsencrypt/live/notifications.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/notifications.example.com/privkey.pem;

    location / {
        proxy_pass         http://localhost:80;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

Set `TRUSTED_PROXY_COUNT=1` in `.env` so the API reads the real client IP from `X-Forwarded-For`.

## Rate Limiting with Redis

By default, rate limits are stored in memory (per process). For multi-replica deployments, point rate limits at Redis so all replicas share counters:

```
RATE_LIMIT_STORAGE_URI=redis://:your-password@your-redis-host:6379/1
```

## TLS / HTTPS

**Certbot (Let's Encrypt):**

```bash
certbot --nginx -d notifications.example.com
```

**Cloudflare Proxy:** Set the origin to HTTP and let Cloudflare handle TLS. Set `TRUSTED_PROXY_COUNT=1` and configure `FRONTEND_URL` / `PUBLIC_BASE_URL` with the `https://` scheme.
