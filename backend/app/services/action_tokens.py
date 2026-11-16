"""
Action tokens: short-lived signed JWTs for email verification, password reset, and invitations.
Uses the same jwt_secret as access tokens but with a distinct 'purpose' claim.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import HTTPException, status

from app.config import get_settings


def _get_secret() -> str:
    settings = get_settings()
    secret = settings.jwt_secret
    if not secret or len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT secret is not configured or too short (minimum 32 characters required)",
        )
    return secret


def make_verify_email_token(user_id: UUID) -> str:
    """24-hour email verification token."""
    secret = _get_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "verify_email",
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=24)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def make_reset_token(user_id: UUID, password_hash: str) -> str:
    """1-hour password reset token. Embeds first 16 hex chars of sha256(password_hash) as 'pwf'."""
    secret = _get_secret()
    now = datetime.now(timezone.utc)
    pwf = hashlib.sha256(password_hash.encode()).hexdigest()[:16]
    payload = {
        "purpose": "reset_password",
        "sub": str(user_id),
        "pwf": pwf,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def make_invite_token(invitation_id: UUID) -> str:
    """7-day invitation token."""
    secret = _get_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "purpose": "invite",
        "sub": str(invitation_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, expected_purpose: str) -> dict:
    """
    Decode and validate an action token.
    Raises HTTP 400 if expired, invalid, or wrong purpose.
    Returns the full payload dict on success.
    """
    secret = _get_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    if payload.get("purpose") != expected_purpose:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    return payload

