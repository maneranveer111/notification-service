from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.database import get_db
from app.api.notifications import router as notifications_router
from app.api.webhooks import router as webhooks_router
from app.api.admin import router as admin_router
from app.api.templates import router as templates_router
from app.limiter import limiter, rate_limit_exceeded_handler
from app.security import ClientRateLimitExceeded

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

app.include_router(notifications_router)
app.include_router(webhooks_router)
app.include_router(admin_router)
app.include_router(templates_router)

@app.get("/health")
def health():
    return {"status" : "ok", "service" : settings.app_name}

@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    version = db.execute(text("SELECT version();")).scalar()
    return {"status": "ok", "db" : "connected", "version" : version}