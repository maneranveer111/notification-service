# Production Deployment Guide

This guide covers deploying the Notification Service to Render (API + Celery worker) and Vercel (frontend).

**Architecture**

| Component | Hosting |
|---|---|
| Frontend (Vite/React) | Vercel Free |
| FastAPI backend | Render Web Service |
| Celery worker + Beat | Render Web Service (via `worker_wrapper.py`) |
| PostgreSQL | Neon |
| Redis | Redis Cloud |
| Transactional email | Brevo or SMTP (configured via env vars) |
| SMS | Twilio (configured via env vars) |

---

## Deployment Order

**Follow this exact order to avoid startup failures:**

1. Create and configure Neon database
2. Create and configure Redis Cloud database
3. Run Alembic migrations against Neon
4. Deploy API service on Render
5. Deploy worker service on Render
6. Deploy frontend on Vercel

---

## Step 1 — Neon Database

1. Create an account at [neon.tech](https://neon.tech).
2. Create a new project. Select the region closest to your Render `oregon` region (US West).
3. Copy the connection string from the Neon dashboard. It looks like:
   ```
   postgresql://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require
   ```
4. Keep this value as `DATABASE_URL`. You will need it in steps 3, 4, and 5.

> The `?sslmode=require` query parameter must be present. Neon enforces TLS.

---

## Step 2 — Redis Cloud

1. Create an account at [redis.com/try-free](https://redis.com/try-free/).
2. Create a free database. Select the region closest to `us-west-2` (Oregon).
3. Copy the public endpoint and password. Construct the Redis URL:
   ```
   redis://:<password>@<host>:<port>
   ```
4. Keep this value as `REDIS_URL`. It is also used for `RATE_LIMIT_STORAGE_URI`.

---

## Step 3 — Run Alembic Migrations

Migrations must be run **once** before the API service receives its first request.

Run this command from your local machine (requires Python 3.11 and the backend dependencies installed):

```bash
cd backend
DATABASE_URL="postgresql://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require" \
  alembic upgrade head
```

Replace the connection string with your actual Neon URL.

Verify success:

```bash
DATABASE_URL="<neon-url>" alembic current
```

The output should show the head revision with `(head)`.

> Alternatively, you can configure a Render pre-deploy command on the API service:
> `alembic upgrade head`
> This runs before each deploy. Only do this if you understand the implications for rollback.

---

## Step 4 — Render API Service

### Option A: Render Blueprint (recommended)

Connect your repository to Render and let it auto-detect `render.yaml` at the repo root. Render will create both services. Then manually enter all `sync: false` environment variables in the Render dashboard for each service.

### Option B: Manual setup

1. In the Render dashboard, click **New → Web Service**.
2. Connect your repository.
3. Configure:

| Setting | Value |
|---|---|
| **Name** | `notification-api` |
| **Region** | Oregon (US West) |
| **Root Directory** | `backend` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Health Check Path** | `/health` |
| **Plan** | Free |

4. Add all environment variables from the **API Environment Variables** table below.

---

## Step 5 — Render Worker Service

1. In the Render dashboard, click **New → Web Service**.
2. Connect the same repository.
3. Configure:

| Setting | Value |
|---|---|
| **Name** | `notification-worker` |
| **Region** | Oregon (US West) |
| **Root Directory** | `backend` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python worker_wrapper.py` |
| **Health Check Path** | `/` |
| **Plan** | Free |

4. Add all environment variables from the **Worker Environment Variables** table below.

The worker consumes three queues: `notification_service_queue_high`, `notification_service_queue`, and `notification_service_queue_low`. Celery Beat is enabled on the worker only (`ENABLE_BEAT=true`).

---

## Step 6 — Vercel Frontend

1. In the Vercel dashboard, click **Add New → Project**.
2. Import your repository.
3. Configure:

| Setting | Value |
|---|---|
| **Root Directory** | `frontend` |
| **Framework Preset** | Vite |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |

4. Add this environment variable under **Settings → Environment Variables**:

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://<your-api-service>.onrender.com` |

5. Deploy. The `frontend/vercel.json` SPA rewrite rule is already in place.

After deploy, verify the frontend loads at `https://<your-project>.vercel.app/login` and that network requests target your Render API URL.

---

## Environment Variable Checklist

### Generate secrets locally

Before filling in the Render dashboard, generate the required secrets:

```bash
# API_KEY (min 24 chars)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# JWT_SECRET (min 32 chars)
python -c "import secrets; print(secrets.token_urlsafe(48))"

# ENCRYPTION_KEY (Fernet key)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# UNSUBSCRIBE_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"

# WEBHOOK_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"

# METRICS_TOKEN
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### API Service Environment Variables

Set these in the Render dashboard for `notification-api`:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `LOG_FORMAT` | `json` |
| `DATABASE_URL` | Neon connection string |
| `REDIS_URL` | Redis Cloud URL |
| `API_KEY` | Generated secret (min 24 chars) |
| `JWT_SECRET` | Generated secret (min 32 chars) |
| `ENCRYPTION_KEY` | Generated Fernet key |
| `UNSUBSCRIBE_SECRET` | Generated secret |
| `WEBHOOK_SECRET` | Generated secret |
| `PUBLIC_BASE_URL` | `https://<api-service>.onrender.com` |
| `FRONTEND_URL` | `https://<project>.vercel.app` |
| `FRONTEND_PUBLIC_URL` | `https://<project>.vercel.app` |
| `SIGNUP_MODE` | `invite_only` |
| `REQUIRE_EMAIL_VERIFICATION` | `true` |
| `SYSTEM_MAIL_BACKEND` | `provider` |
| `CELERY_QUEUE` | `notification_service_queue` |
| `EMAIL_PROVIDER_ORDER` | `brevo,smtp` |
| `BREVO_API_KEY` | From Brevo dashboard |
| `BREVO_FROM_EMAIL` | Verified sender address in Brevo |
| `BREVO_FROM_NAME` | Display name (e.g. `Notification Service`) |
| `SMTP_HOST` | SMTP relay hostname |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `SMTP_FROM_EMAIL` | Sender email address |
| `SMTP_PORT` | `587` |
| `SMTP_USE_TLS` | `true` |
| `TWILIO_ACCOUNT_SID` | From Twilio console |
| `TWILIO_AUTH_TOKEN` | From Twilio console |
| `TWILIO_FROM_NUMBER` | E.164 format (e.g. `+15551234567`) |
| `METRICS_TOKEN` | Generated secret |
| `TRUSTED_PROXY_COUNT` | `1` |
| `RATE_LIMIT_STORAGE_URI` | Same Redis Cloud URL as `REDIS_URL` |
| `QUOTA_ENABLED` | `true` |
| `TURNSTILE_SECRET_KEY` | From Cloudflare (optional — leave blank to disable CAPTCHA) |
| `TURNSTILE_SITE_KEY` | From Cloudflare (optional) |
| `WEBHOOK_VERIFY` | `true` |
| `WEBHOOK_CHANNEL_ALLOWED_HOSTS` | `hooks.slack.com,discord.com,discordapp.com` |
| `SCHEDULE_MAX_DAYS` | `30` |
| `BULK_MAX_RECIPIENTS` | `200` |
| `MAX_WORKSPACES_PER_USER` | `5` |
| `DB_POOL_SIZE` | `3` |
| `DB_MAX_OVERFLOW` | `2` |
| `DB_POOL_TIMEOUT` | `30` |
| `DB_POOL_RECYCLE` | `1800` |

**Do NOT set `ENABLE_BEAT` on the API service.**

### Worker Service Environment Variables

Set these in the Render dashboard for `notification-worker`. Variables marked ★ must be **identical** to the API service.

| Variable | Value | Note |
|---|---|---|
| `ENVIRONMENT` | `production` | ★ |
| `LOG_FORMAT` | `json` | ★ |
| `DATABASE_URL` | Neon connection string | ★ |
| `REDIS_URL` | Redis Cloud URL | ★ |
| `API_KEY` | Same as API | ★ |
| `JWT_SECRET` | Same as API | ★ |
| `ENCRYPTION_KEY` | Same as API | ★ |
| `UNSUBSCRIBE_SECRET` | Same as API | ★ |
| `WEBHOOK_SECRET` | Same as API | ★ |
| `PUBLIC_BASE_URL` | Same as API | ★ |
| `FRONTEND_URL` | Same as API | ★ |
| `FRONTEND_PUBLIC_URL` | Same as API | ★ |
| `SIGNUP_MODE` | `invite_only` | ★ |
| `REQUIRE_EMAIL_VERIFICATION` | `true` | ★ |
| `SYSTEM_MAIL_BACKEND` | `provider` | ★ |
| `CELERY_QUEUE` | `notification_service_queue` | ★ |
| `EMAIL_PROVIDER_ORDER` | `brevo,smtp` | ★ |
| `BREVO_API_KEY` | Same as API | ★ |
| `BREVO_FROM_EMAIL` | Same as API | ★ |
| `BREVO_FROM_NAME` | Same as API | ★ |
| `SMTP_HOST` | Same as API | ★ |
| `SMTP_USER` | Same as API | ★ |
| `SMTP_PASSWORD` | Same as API | ★ |
| `SMTP_FROM_EMAIL` | Same as API | ★ |
| `SMTP_PORT` | `587` | ★ |
| `SMTP_USE_TLS` | `true` | ★ |
| `TWILIO_ACCOUNT_SID` | Same as API | ★ |
| `TWILIO_AUTH_TOKEN` | Same as API | ★ |
| `TWILIO_FROM_NUMBER` | Same as API | ★ |
| `METRICS_TOKEN` | Same as API | ★ |
| `TRUSTED_PROXY_COUNT` | `1` | ★ |
| `RATE_LIMIT_STORAGE_URI` | Same as API | ★ |
| `QUOTA_ENABLED` | `true` | ★ |
| `TURNSTILE_SECRET_KEY` | Same as API | ★ |
| `WEBHOOK_CHANNEL_ALLOWED_HOSTS` | `hooks.slack.com,discord.com,discordapp.com` | ★ |
| `SCHEDULE_MAX_DAYS` | `30` | ★ |
| `BULK_MAX_RECIPIENTS` | `200` | ★ |
| `ENABLE_BEAT` | `true` | **Worker only** |
| `DB_POOL_SIZE` | `3` | |
| `DB_MAX_OVERFLOW` | `2` | |
| `DB_POOL_TIMEOUT` | `30` | |
| `DB_POOL_RECYCLE` | `1800` | |

### Vercel (Frontend) Environment Variables

| Variable | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://<api-service>.onrender.com` |

---

## Health Check URLs

After deployment, verify these endpoints respond correctly:

| URL | Expected response |
|---|---|
| `https://<api>.onrender.com/health` | `{"status":"ok","service":"Notification Service"}` |
| `https://<worker>.onrender.com/` | `Celery worker running` |
| `https://<project>.vercel.app/` | Frontend HTML (redirects to `/login`) |

---

## Production Smoke Tests

Run these after all services are live:

```bash
# 1. API health
curl https://<api>.onrender.com/health

# 2. API config endpoint (returns public configuration)
curl https://<api>.onrender.com/public/config

# 3. Auth — expect 422 (missing body) or 401 (bad credentials), not 500
curl -X POST https://<api>.onrender.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"wrong"}'

# 4. Worker health
curl https://<worker>.onrender.com/

# 5. Deep health check (requires metrics token or superadmin JWT)
curl https://<api>.onrender.com/health/deep \
  -H "Authorization: Bearer <METRICS_TOKEN>"

# 6. Frontend loads
curl -I https://<project>.vercel.app/
```

---

## Rollback Notes

- **Frontend**: Vercel keeps every deployment. Roll back via Vercel dashboard → Deployments → Promote previous deployment.
- **API / Worker**: Render keeps previous deploys. Roll back via Render dashboard → Manual Deploy → select a previous commit.
- **Database**: Alembic does not auto-downgrade. If a migration must be reversed, run `alembic downgrade -1` manually with the Neon connection string before rolling back the application code.
- **Render free tier cold starts**: After 15 minutes of inactivity, the free tier spins down. The first request will take 30–60 seconds. This is a Render platform limitation, not a bug.

---

## Notes

- `SIGNUP_MODE=invite_only` is set on both services. Public signup is disabled. New users require an invitation from an existing admin.
- `ENABLE_BEAT=true` is set only on the worker service, ensuring exactly one Celery Beat instance runs in production.
- The Beat schedule file (`/tmp/celerybeat-schedule`) is ephemeral on Render. It is recreated on startup from the schedule defined in `app/celery_app.py`. Scheduled tasks (`notifications.requeue_stale` every 120 s, `notifications.dispatch_scheduled` every 30 s) are unaffected.
- If you use a custom Vercel domain, add it to `FRONTEND_URL` on both Render services as a comma-separated value (e.g. `https://app.example.com,https://project.vercel.app`).
- Neon connection strings must include `?sslmode=require`. The SQLAlchemy engine reads this directly from the DSN.
