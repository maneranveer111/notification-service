from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.services.client_ip import client_ip

router = APIRouter(prefix="/public", tags=["Public"])
settings = get_settings()


@router.get("/config")
@limiter.limit("60/minute", key_func=client_ip)
def get_public_config(request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    user_count = db.scalar(select(func.count()).select_from(User))
    needs_setup = (user_count == 0) and (settings.signup_mode != "closed")

    return {
        "app_name": settings.app_name,
        "signup_mode": settings.signup_mode,
        "require_email_verification": settings.require_email_verification,
        "turnstile_site_key": settings.turnstile_site_key,
        "needs_setup": needs_setup,
    }
