from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.api_client import ApiClient
from app.models.user import User
from app.services.jwt_tokens import decode_access_token
from app.services.rate_limit import check_rate_limit

settings = get_settings()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class Principal:
    client_id: UUID | None = None
    is_admin: bool = False
    can_write: bool = True
    sees_all: bool = False
    user_id: UUID | None = None
    email: str | None = None
    role: str | None = None


class ClientRateLimitExceeded(Exception):
    def __init__(self, limit: str):
        self.limit = limit


def get_principal(
    request: Request,
    api_key: str = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Principal:
    # Check Authorization header first (Bearer JWT)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        try:
            user_uuid = UUID(user_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        # Load user from DB on every request
        user = db.get(User, user_uuid)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        if user.role == "admin":
            return Principal(
                client_id=None,
                is_admin=True,
                can_write=True,
                sees_all=True,
                user_id=user.id,
                email=user.email,
                role="admin",
            )
        else:  # viewer
            return Principal(
                client_id=None,
                is_admin=False,
                can_write=False,
                sees_all=True,
                user_id=user.id,
                email=user.email,
                role="viewer",
            )

    # Fallback to existing X-API-Key logic
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is missing. Pass it as X-API-Key header.",
        )

    # Master key matches settings.api_key
    if hmac.compare_digest(api_key, settings.api_key):
        return Principal(
            client_id=None,
            is_admin=True,
            can_write=True,
            sees_all=True,
            role="master",
        )

    # Client key lookup
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    client = db.execute(
        select(ApiClient).where(
            ApiClient.key_hash == key_hash,
            ApiClient.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    # Enforce per-client rate limit
    if not check_rate_limit(client.id, client.rate_limit_per_minute):
        raise ClientRateLimitExceeded(f"{client.rate_limit_per_minute}/minute")

    # Update last_used_at only when null or older than 5 minutes
    now = datetime.now(timezone.utc)
    last_used = client.last_used_at
    if last_used is not None and last_used.tzinfo is None:
        last_used = last_used.replace(tzinfo=timezone.utc)

    if last_used is None or (now - last_used) > timedelta(minutes=5):
        client.last_used_at = now
        db.commit()

    return Principal(
        client_id=client.id,
        is_admin=False,
        can_write=True,
        sees_all=False,
        role="client",
    )


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if principal is True:
        return Principal(client_id=None, is_admin=True, can_write=True, sees_all=True, role="master")
    if not isinstance(principal, Principal) or not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return principal


def require_write(principal: Principal = Depends(get_principal)) -> Principal:
    if principal is True:
        return Principal(client_id=None, is_admin=True, can_write=True, sees_all=True, role="master")
    if not isinstance(principal, Principal) or not principal.can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required.",
        )
    return principal


verify_api_key = get_principal
