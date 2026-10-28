from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from uuid import UUID

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.api_client import ApiClient
from app.services.rate_limit import check_rate_limit

settings = get_settings()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class Principal:
    client_id: UUID | None
    is_admin: bool


class ClientRateLimitExceeded(Exception):
    def __init__(self, limit: str):
        self.limit = limit


def get_principal(
    api_key: str = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Principal:
    # Case 1: Missing header
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is missing. Pass it as X-API-Key header.",
        )

    # Case 2: Master key matches settings.api_key
    if hmac.compare_digest(api_key, settings.api_key):
        return Principal(client_id=None, is_admin=True)

    # Case 3: Client key lookup
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

    return Principal(client_id=client.id, is_admin=False)


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not isinstance(principal, Principal) or not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return principal


verify_api_key = get_principal
