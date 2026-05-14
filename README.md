# Notification Service Microservice

A production-ready standalone microservice for sending **Email** and **SMS** notifications asynchronously. Built with FastAPI, Celery, Redis, PostgreSQL, SendGrid, and Twilio.

---

## What This Project Does

Other applications (shopping apps, food delivery apps, hospital systems) can call this service to send notifications without worrying about:
- Slow email/SMS delivery blocking their response time
- Retry logic when providers fail
- Tracking delivery status
- Rate limiting and authentication

---

## Architecture

Client App
│
▼
POST /notifications/email or /sms
│
▼
┌─────────────────┐
│ FastAPI │ → validates input → saves to PostgreSQL (status=pending)
│ (Port 8000) │ → queues job in Redis → responds instantly
└─────────────────┘
│
▼
┌─────────────────┐
│ Redis │ holds jobs in queue
│ (Port 6379) │
└─────────────────┘
│
▼
┌─────────────────┐
│ Celery Worker │ → picks up job → sends via SendGrid/Twilio
│ (Background) │ → updates DB (status=sent/failed)
│ │ → retries automatically on failure
└─────────────────┘


---

## Tech Stack

| Technology | Purpose |
|-----------|---------|
| FastAPI | REST API framework |
| PostgreSQL | Persistent notification storage |
| SQLAlchemy | ORM for database interaction |
| Alembic | Database schema migrations |
| Celery | Background task processing |
| Redis | Message broker / job queue |
| SendGrid | Email delivery provider |
| Twilio | SMS delivery provider |
| Docker Compose | Redis containerization |
| Pydantic | Request/response validation |
| slowapi | Rate limiting |

---

## Features

- ✅ Queue email notifications via REST API
- ✅ Queue SMS notifications via REST API
- ✅ Asynchronous background processing (Celery)
- ✅ Automatic retry logic (up to 3 attempts)
- ✅ Manual retry endpoint for failed notifications
- ✅ Real-time status tracking (pending/processing/sent/failed/retrying)
- ✅ Notification history with filtering and pagination
- ✅ API key authentication
- ✅ Rate limiting per client
- ✅ Provider message ID tracking (SendGrid/Twilio)
- ✅ Database migrations with Alembic
- ✅ Automated unit tests

---

## Project Structure
notification-service/
│
├── app/
│ ├── api/
│ │ └── notifications.py # API endpoints
│ ├── models/
│ │ └── notification.py # Database model
│ ├── schemas/
│ │ └── notification.py # Pydantic schemas
│ ├── services/
│ │ ├── email_service.py # SendGrid integration
│ │ └── sms_service.py # Twilio integration
│ ├── tasks/
│ │ └── notification_tasks.py # Celery background tasks
│ ├── celery_app.py # Celery configuration
│ ├── config.py # Settings from .env
│ ├── database.py # DB connection setup
│ ├── limiter.py # Rate limiting
│ ├── main.py # FastAPI app entry point
│ └── security.py # API key authentication
│
├── alembic/ # Database migrations
├── tests/ # Automated tests
├── docker-compose.yml # Redis container
├── requirements.txt # Python dependencies
├── .env.example # Environment variables template
└── README.md


---

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL
- Docker Desktop (for Redis)
- SendGrid account
- Twilio account

---

### 1) Clone the repository

```bash
git clone https://github.com/your-username/notification-service.git
cd notification-service

2) Create virtual environment

python -m venv venv
source venv/Scripts/activate  # Windows
source venv/bin/activate       # Mac/Linux

3) Install dependencies
pip install -r requirements.txt

4) Setup environment variables
cp .env.example .env

Open .env and fill in your values:
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/notification_db
REDIS_URL=redis://localhost:6379
SENDGRID_API_KEY=your_sendgrid_api_key
SENDGRID_FROM_EMAIL=your_verified_sender@gmail.com
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
API_KEY=your-secret-api-key

5) Create PostgreSQL database
psql -U postgres -c "CREATE DATABASE notification_db;"

6) Run database migrations
alembic upgrade head

7) Start Redis
docker compose up -d

8) Start Celery worker
celery -A app.celery_app.celery worker --loglevel=info -P solo

9) Start FastAPI server
uvicorn app.main:app --reload

API Reference
Authentication
All endpoints (except /health) require an API key in the request header:

X-API-Key: your-secret-api-key

Endpoints

Health Check
GET /health
Response:
JSON
{
  "status": "ok",
  "service": "Notification Service"
}


Send Email
POST /notifications/email
Request body:
JSON
{
  "recipient": "user@example.com",
  "subject": "Hello",
  "body": "Your order has been confirmed!"
}
Response:
JSON
{
  "id": "3b7d0d3a-9f51-4df0-9c64-b2a3c4d5e6f7",
  "status": "pending",
  "channel": "email"
}


Send SMS
POST /notifications/sms
Request body:
JSON
{
  "recipient": "+919XXXXXXXXX",
  "message": "Your OTP is 1234"
}
Response:
JSON
{
  "id": "5725e7a0-f112-436e-b8da-f31a7eb652c5",
  "status": "pending",
  "channel": "sms"
}

Check Notification Status
GET /notifications/{id}
Response:
JSON
{
  "id": "3b7d0d3a-9f51-4df0-9c64-b2a3c4d5e6f7",
  "channel": "email",
  "recipient": "user@example.com",
  "subject": "Hello",
  "body": "Your order has been confirmed!",
  "status": "sent",
  "attempt_count": 1,
  "max_attempts": 3,
  "provider": "sendgrid",
  "provider_message_id": "cpxiBB3NRRqlU-VCg6qMAg",
  "error_message": null,
  "sent_at": "2024-01-01T10:00:00+05:30",
  "created_at": "2024-01-01T10:00:00+05:30",
  "updated_at": "2024-01-01T10:00:00+05:30"
}

List Notifications
GET /notifications?status=sent&channel=email&limit=10&offset=0

Query parameters:

Parameter	Type	Description
status	string	Filter by status (pending/sent/failed)
channel	string	Filter by channel (email/sms)
limit	integer	Results per page (default: 50, max: 200)
offset	integer	Skip N results (default: 0)


Retry Failed Notification
POST /notifications/{id}/retry
Response:
JSON
{
  "id": "3b7d0d3a-9f51-4df0-9c64-b2a3c4d5e6f7",
  "status": "pending",
  "channel": "email"
}

Rate Limits
Endpoint	Limit
POST /notifications/email	10 requests/minute
POST /notifications/sms	10 requests/minute
POST /notifications/{id}/retry	10 requests/minute
GET /notifications	60 requests/minute
GET /notifications/{id}	60 requests/minute


Notification Status Flow
pending → processing → sent ✅
                    ↘
                     failed ❌ (after max retries)
                    ↗
              retrying 🔄 (automatic retry)

Running Tests
pytest -v

Interactive API Docs
FastAPI provides automatic interactive documentation:
http://127.0.0.1:8000/docs


Environment     Variables
Variable	    Required	Description
DATABASE_URL	    ✅   PostgreSQL connection string
REDIS_URL	        ✅    Redis connection string
API_KEY     	    ✅	   Secret key for API authentication
SENDGRID_API_KEY	✅	SendGrid API key for email
SENDGRID_FROM_EMAIL	✅	Verified sender email
TWILIO_ACCOUNT_SID	✅	Twilio Account SID
TWILIO_AUTH_TOKEN	✅	Twilio Auth Token
TWILIO_FROM_NUMBER	✅	Twilio phone number

Future Improvements
 Per-client unique API keys stored in database
 JWT authentication for user-facing dashboard
 Webhook support for delivery status updates
 HTML email templates support
 Email open/click tracking
 Dashboard UI for notification monitoring
 Docker containerization for full stack
 CI/CD pipeline
 Cloud deployment (AWS/GCP/Railway)

