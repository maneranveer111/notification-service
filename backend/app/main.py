from datetime import datetime, timezone
from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
import sys
import time
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.accounts import router as accounts_router
from app.api.public import router as public_router
from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.invitations import router as invitations_router, user_invitations_router
from app.api.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL, router as metrics_router
from app.api.notifications import router as notifications_router
from app.api.providers import router as providers_router
from app.api.stats import router as stats_router
from app.api.suppressions import router as suppressions_router
from app.api.templates import router as templates_router
from app.api.unsubscribe import router as unsubscribe_router
from app.api.webhooks import router as webhooks_router
from app.api.workspaces import router as workspaces_router
from app.config import get_settings
from app.database import get_db
from app.limiter import limiter, rate_limit_exceeded_handler
from app.models.user import User
from app.security import ClientRateLimitExceeded
from app.services.jwt_tokens import decode_access_token
from app.services.quota import QuotaExceeded
from app.services.startup_checks import validate_production_or_raise

settings = get_settings()


class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "notification_id"):
            log_obj["notification_id"] = str(record.notification_id)
        if hasattr(record, "request_id"):
            log_obj["request_id"] = str(record.request_id)
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def configure_logging():
    if settings.log_format == "json":
        root = logging.getLogger()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONLogFormatter())
        root.handlers = [handler]


configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_or_raise(settings)
    logging.getLogger("app.main").info(
        "Startup settings: environment=%s, signup_mode=%s, require_email_verification=%s, system_mail_backend=%s, queues=%s",
        settings.environment,
        settings.signup_mode,
        settings.require_email_verification,
        settings.system_mail_backend,
        settings.get_queue_names(),
    )
    from app.database import SessionLocal
    from app.services.tenancy import ensure_default_workspace
    try:
        with SessionLocal() as db:
            ensure_default_workspace(db)
    except Exception:
        logging.getLogger("app.main").error("Database is not migrated: run python -m scripts.migrate")
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Request-ID"],
)

app.state.limiter = limiter

app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


@app.exception_handler(ClientRateLimitExceeded)
def client_rate_limit_exceeded_handler(request: Request, exc: ClientRateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Try again later.",
            "limit": exc.limit,
            "retry_after": "60 seconds",
        },
        headers={"Retry-After": "60"},
    )


@app.exception_handler(QuotaExceeded)
async def quota_exceeded_handler(request: Request, exc: QuotaExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=exc.to_dict(),
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        content = dict(exc.detail)
        if "detail" not in content and "message" in content:
            content["detail"] = content["message"]
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.middleware("http")
async def request_id_and_metrics_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = req_id

    start_time = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - start_time
        route = request.scope.get("route")
        handler = route.path if route else request.url.path
        HTTP_REQUESTS_TOTAL.labels(method=request.method, handler=handler, status=500).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, handler=handler).observe(duration)
        raise

    duration = time.perf_counter() - start_time
    route = request.scope.get("route")
    handler = route.path if route else request.url.path
    HTTP_REQUESTS_TOTAL.labels(method=request.method, handler=handler, status=response.status_code).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=request.method, handler=handler).observe(duration)

    response.headers["X-Request-ID"] = req_id
    return response


app.include_router(auth_router)
app.include_router(accounts_router)
app.include_router(public_router)
app.include_router(notifications_router)
app.include_router(webhooks_router)
app.include_router(admin_router)
app.include_router(templates_router)
app.include_router(suppressions_router)
app.include_router(unsubscribe_router)
app.include_router(stats_router)
app.include_router(metrics_router)
app.include_router(workspaces_router)
app.include_router(invitations_router)
app.include_router(user_invitations_router)
app.include_router(providers_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    version = db.execute(text("SELECT version();")).scalar()
    return {"status": "ok", "db": "connected", "version": version}


def verify_deep_health_access(request: Request, db: Session = Depends(get_db)):
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if settings.metrics_token and hmac.compare_digest(token, settings.metrics_token):
            return True
        try:
            payload = decode_access_token(token)
            user_id = UUID(payload.get("sub"))
            user = db.get(User, user_id)
            if not user or not user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
            if not user.is_superadmin:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superadmin access required.")
            return True
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    api_key = request.headers.get("X-API-Key")
    if api_key and settings.api_key and hmac.compare_digest(api_key, settings.api_key):
        return True

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


@app.get("/health/deep")
def health_deep(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(verify_deep_health_access),
):
    try:
        db.execute(text("SELECT 1;")).scalar()
        db_status = "ok"
    except Exception:
        db_status = "error"

    redis_status = "error"
    queues = {}
    q_names = settings.get_queue_names()
    try:
        from app.services.rate_limit import get_redis_client
        r = get_redis_client()
        if r.ping():
            redis_status = "ok"
            for q in q_names:
                try:
                    queues[q] = r.llen(q)
                except Exception:
                    queues[q] = 0
    except Exception:
        redis_status = "error"
        for q in q_names:
            queues[q] = 0

    try:
        from app.celery_app import celery
        res = celery.control.inspect(timeout=1).ping()
        worker_status = "ok" if res else "none"
    except Exception:
        worker_status = "none"

    beat_status = "none"
    try:
        from app.services.rate_limit import get_redis_client
        import time as _time
        r = get_redis_client()
        raw = r.get("beat:last_run")
        if raw is not None:
            age = _time.time() - float(raw)
            beat_status = "ok" if age <= 120 else "stale"
    except Exception:
        pass

    migrations_status = "unknown"
    try:
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from alembic.config import Config

        ini_path = "backend/alembic.ini" if os.path.exists("backend/alembic.ini") else "alembic.ini"
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option(
            "script_location",
            "backend/alembic" if os.path.exists("backend/alembic") else "alembic",
        )
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        bind = db.get_bind()
        with bind.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        if current_rev == head_rev and head_rev is not None:
            migrations_status = "ok"
        else:
            migrations_status = "behind"
    except Exception:
        migrations_status = "unknown"

    return {
        "db": db_status,
        "redis": redis_status,
        "worker": worker_status,
        "beat": beat_status,
        "migrations": migrations_status,
        "queues": queues,
        "environment": settings.environment,
        "version": os.environ.get("APP_VERSION", "dev"),
    }
