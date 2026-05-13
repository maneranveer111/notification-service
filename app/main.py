from fastapi import FastAPI, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.database import get_db
from app.api.notifications import router as notifications_router
from app.limiter import limiter, rate_limit_exceeded_handler

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug
)

app.state.limiter = limiter

app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.include_router(notifications_router)

@app.get("/health")
def health():
    return {"status" : "ok", "service" : settings.app_name}

@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    version = db.execute(text("SELECT version();")).scalar()
    return {"status": "ok", "db" : "connected", "version" : version}