from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.schemas.auth import AuthMeResponse, LoginRequest, TokenResponse, UserAuthInfo
from app.security import Principal, get_principal
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()

_DUMMY_HASH = hash_password("not-a-real-password-timing-defense")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))

    if not user:
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
    )
    expires_in_seconds = settings.jwt_expire_minutes * 60

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in_seconds,
        user=UserAuthInfo(
            id=user.id,
            email=user.email,
            role=user.role,
        ),
    )


@router.get("/me", response_model=AuthMeResponse)
def get_current_user_info(principal: Principal = Depends(get_principal)):
    return AuthMeResponse(
        id=principal.user_id,
        email=principal.email,
        role=principal.role,
        can_write=principal.can_write,
        is_admin=principal.is_admin,
    )

