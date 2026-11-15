from datetime import datetime, timezone
import json
import logging
import sys
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
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
from app.security import ClientRateLimitExceeded
from app.services.quota import QuotaExceeded

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

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
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
