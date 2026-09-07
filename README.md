# Notification Service

A full-stack notification service supporting **email** and **SMS** delivery, with a live dashboard to send notifications and track their status in real time. Built with FastAPI, Celery, and React.

**Live demo:**
- Frontend: `https://notification-service-xxxx.vercel.app`
- API: `https://notification-service-api-oj4p.onrender.com`

---

## Features

- Queue email and SMS notifications via a REST API
- Background processing with Celery (non-blocking sends)
- Track notification status: `pending` → `sent` / `failed` / `retrying`
- Manual retry for failed notifications
- API key authentication + rate limiting
- React dashboard: send form, live status list, filters, retry
- Fully responsive UI

---

## Tech Stack

**Backend**
- FastAPI (Python)
- Celery — background task processing
- SQLAlchemy + Alembic — ORM and migrations
- PostgreSQL — persistent storage
- Redis — Celery broker/result backend
- Brevo — transactional email
- Twilio — SMS
- slowapi — rate limiting

**Frontend**
- React + Vite
- Tailwind CSS v4

**Infrastructure**
- Render — API + worker hosting
- Vercel — frontend hosting
- Neon — managed Postgres
- Redis Cloud — managed Redis

---

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌───────────────┐
│   Frontend  │─────▶│   FastAPI    │─────▶│   PostgreSQL  │
│  (Vercel)   │      │   (Render)   │      │    (Neon)     │
└─────────────┘      └──────┬───────┘      └───────────────┘
                             │
                             ▼
                      ┌──────────────┐
                      │ Redis Cloud  │
                      │ (task queue) │
                      └──────┬───────┘
                             │
                             ▼
                      ┌──────────────┐
                      │ Celery Worker│
                      │   (Render)   │
                      └──────┬───────┘
                             │
                 ┌───────────┴───────────┐
                 ▼                       ▼
           ┌──────────┐           ┌──────────┐
           │  Brevo   │           │  Twilio  │
           │ (email)  │           │  (SMS)   │
           └──────────┘           └──────────┘
```

A client sends a request to the API, which persists the notification as `pending` and hands it off to Celery via Redis. The worker picks it up, calls the relevant provider (Brevo or Twilio), and updates the record's status. The frontend polls the API to reflect live status changes.

---

## Project Structure

```
notification-service/
├── backend/
│   ├── alembic/              # DB migrations
│   ├── app/
│   │   ├── api/               # route handlers
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/            # email_service.py, sms_service.py
│   │   ├── tasks/               # Celery task definitions
│   │   ├── celery_app.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── limiter.py
│   │   ├── main.py
│   │   └── security.py
│   ├── worker_wrapper.py      # runs Celery as a free Render web service
│   ├── alembic.ini
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/
    │   │   ├── SendForm.jsx
    │   │   ├── NotificationList.jsx
    │   │   └── Filters.jsx
    │   ├── api.js
    │   └── App.jsx
    └── package.json
```

---

## API Endpoints

All endpoints (except `/health`) require an `X-API-Key` header.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service health check |
| GET | `/health/db` | Database connectivity check |
| POST | `/notifications/email` | Queue an email |
| POST | `/notifications/sms` | Queue an SMS |
| GET | `/notifications` | List notifications (filterable by `status`, `channel`) |
| GET | `/notifications/{id}` | Get a single notification |
| POST | `/notifications/{id}/retry` | Retry a failed notification |

---

## Local Development

### Prerequisites
- Python 3.13+
- Node.js
- A PostgreSQL instance (local or hosted)
- A Redis instance (local or hosted)
- Brevo account (free tier) for email
- Twilio account (trial or paid) for SMS

### Backend

```bash
cd backend
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
# venv\Scripts\activate        # Windows PowerShell
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
cp .env.example .env           # fill in your own values
alembic upgrade head

# Terminal 1
python -m uvicorn app.main:app --reload --port 8001

# Terminal 2
celery -A app.celery_app worker --loglevel=info -Q notification_service_queue --pool=solo
```

> `--pool=solo` is required on Windows (Celery's default prefork pool doesn't work reliably there). On Linux/macOS, prefork works fine and this flag can be dropped.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env           # point VITE_API_BASE_URL at your backend
npm run dev
```

---

## Environment Variables

### Backend (`backend/.env`)

```
DATABASE_URL=postgresql://user:pass@host:port/dbname
REDIS_URL=redis://default:pass@host:port

BREVO_API_KEY=
BREVO_FROM_EMAIL=

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

API_KEY=
APP_NAME=Notification Service
DEBUG=False
FRONTEND_URL=http://localhost:5173
```

### Frontend (`frontend/.env`)

```
VITE_API_BASE_URL=http://localhost:8001
VITE_API_KEY=
```

---

## Deployment

### Backend — Render

Two services are deployed from the same repo, both with **Root Directory** set to `backend`:

**1. API (Web Service)**
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

**2. Worker**
Render's free tier does not include Background Worker services — only Web Services. To run Celery for free, the worker is deployed as a **Web Service** running `worker_wrapper.py`, which starts the real Celery worker in a background thread and binds a minimal dummy HTTP server to `$PORT` just to satisfy Render's health check.
- Build: `pip install -r requirements.txt`
- Start: `python worker_wrapper.py`

Both services share the same environment variables. `celery`'s pool is set to `--pool=solo` in the wrapper — the default `prefork` pool spawns multiple processes and exceeds the 512MB RAM limit on Render's free instance, causing an OOM crash loop.

### Frontend — Vercel
- Root Directory: `frontend`
- Framework: Vite (auto-detected)
- Env vars: `VITE_API_BASE_URL` (pointing to the Render API URL), `VITE_API_KEY`

After deploying the frontend, update `FRONTEND_URL` on the Render API service to the Vercel URL so CORS allows requests from it.

---

## Known Limitations

- **Twilio (SMS):** Running on a trial account, which can only send to phone numbers manually verified in the Twilio console. A paid account removes this restriction.
- **Free-tier cold starts:** Both Render services (API and worker) spin down after ~15 minutes of inactivity. The first request after idling can take 30–50 seconds to respond. *(Workaround planned/in progress.)*
- **Email deliverability:** The sender address is a personal Gmail account rather than an authenticated custom domain, so some emails may land in spam depending on the recipient's provider.
- **API key exposure:** The `X-API-Key` header is sent from the browser, so it's visible in the network tab. This is acceptable for a demo/portfolio project but isn't a substitute for real user authentication in a production system.
- **Neon (Postgres) / Redis Cloud:** Both are on generous free tiers but may have connection idling behavior (auto-sleep/reconnect) under very low traffic.

---

## Possible Future Improvements

- Replace API-key auth with proper user accounts (JWT-based)
- Add webhook support for delivery status callbacks from Brevo/Twilio
- Add pagination controls to the frontend list
- Domain-authenticated sender for better email deliverability
- Upgrade Twilio to remove the verified-number restriction