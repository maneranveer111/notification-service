from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from fastapi import HTTPException, status

from app.config import get_settings


def create_access_token(
    user_id: Any,
    email: str | None = None,
    role: str | None = None,
    workspace_id: Any | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    secret = settings.jwt_secret
    if not secret or len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT secret is not configured or too short (minimum 32 characters required)",
        )

    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    exp = now + expires_delta

    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if email is not None:
        payload["email"] = email
    if role is not None:
        payload["role"] = role
    if workspace_id is not None:
        payload["ws"] = str(workspace_id)

    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    secret = settings.jwt_secret
    if not secret or len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT secret is not configured or too short (minimum 32 characters required)",
        )

    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
