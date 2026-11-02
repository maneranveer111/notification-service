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
from app.models.workspace import Membership
from app.services.jwt_tokens import decode_access_token
from app.services.rate_limit import check_rate_limit
from app.services.tenancy import get_default_workspace_id

settings = get_settings()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class Principal:
    workspace_id: UUID | None = None
    workspace_role: str | None = None  # "owner" | "admin" | "viewer"
    is_admin: bool = False             # True for workspace owner/admin or master key
    can_write: bool = True             # True for owner/admin/keys, False for viewer
    is_superadmin: bool = False        # True for users with is_superadmin=True or master key
    client_id: UUID | None = None      # Attribution for API keys only
    user_id: UUID | None = None
    email: str | None = None
    role: str | None = None            # Legacy helper


class ClientRateLimitExceeded(Exception):
    def __init__(self, limit: str):
        self.limit = limit


def get_user_principal(
    request: Request,
    api_key: str = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Principal:
    """
    Resolve principal user without requiring an active workspace membership.
    Used for /auth/me, /workspaces, /auth/switch-workspace.
    """
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

        user = db.get(User, user_uuid)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        if user.password_changed_at:
            token_iat = payload.get("iat")
            if token_iat is not None and token_iat < user.password_changed_at.timestamp():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                )

        # Attempt to resolve workspace membership if available
        claim_ws = payload.get("ws")
        membership = None
        if claim_ws:
            try:
                target_ws_id = UUID(claim_ws)
                membership = db.get(Membership, (user.id, target_ws_id))
            except ValueError:
                pass
        else:
            if user.last_workspace_id:
                membership = db.get(Membership, (user.id, user.last_workspace_id))
            if not membership:
                membership = db.execute(
                    select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at.asc())
                ).scalars().first()

        if membership:
            ws_role = membership.role
            is_adm = ws_role in ("owner", "admin")
            return Principal(
                workspace_id=membership.workspace_id,
                workspace_role=ws_role,
                is_admin=is_adm,
                can_write=is_adm,
                is_superadmin=user.is_superadmin,
                user_id=user.id,
                email=user.email,
                role=ws_role,
            )

        # No membership: still a valid user principal
        return Principal(
            workspace_id=None,
            workspace_role=None,
            is_admin=user.is_superadmin,
            can_write=True,
            is_superadmin=user.is_superadmin,
            user_id=user.id,
            email=user.email,
            role="user",
        )

    # Master key fallback
    if api_key and hmac.compare_digest(api_key, settings.api_key):
        default_ws = get_default_workspace_id(db)
        return Principal(
            workspace_id=default_ws,
            workspace_role="admin",
            is_admin=True,
            can_write=True,
            is_superadmin=True,
            role="master",
        )

    # Client key fallback
    if api_key:
        key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        client = db.execute(
            select(ApiClient).where(ApiClient.key_hash == key_hash, ApiClient.is_active.is_(True))
        ).scalar_one_or_none()
        if client:
            return Principal(
                workspace_id=client.workspace_id,
                client_id=client.id,
                is_admin=False,
                can_write=True,
                is_superadmin=False,
                role="client",
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def get_principal(
    request: Request,
    api_key: str = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Principal:
    """
    Standard principal resolver requiring active tenant workspace context.
    """
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

        user = db.get(User, user_uuid)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        if user.password_changed_at:
            token_iat = payload.get("iat")
            if token_iat is not None and token_iat < user.password_changed_at.timestamp():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                )

        if settings.require_email_verification and not user.email_verified_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified",
            )

        # 1. Choose workspace: claim 'ws' -> user.last_workspace_id -> first membership
        claim_ws = payload.get("ws")
        if claim_ws:
            try:
                target_ws_id = UUID(claim_ws)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token workspace claim",
                )
            membership = db.get(Membership, (user.id, target_ws_id))
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No access to requested workspace",
                )
        else:
            target_ws_id = user.last_workspace_id
            membership = None
            if target_ws_id:
                membership = db.get(Membership, (user.id, target_ws_id))

            if not membership:
                # Fallback to first membership in DB
                membership = db.execute(
                    select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at.asc())
                ).scalars().first()

            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No workspace access",
                )

        ws_role = membership.role
        is_adm = ws_role in ("owner", "admin")
        can_w = ws_role in ("owner", "admin")

        return Principal(
            workspace_id=membership.workspace_id,
            workspace_role=ws_role,
            is_admin=is_adm,
            can_write=can_w,
            is_superadmin=user.is_superadmin,
            user_id=user.id,
            email=user.email,
            role=ws_role,
        )

    # Header-based API key logic
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is missing. Pass it as X-API-Key header.",
        )

    # Master key matches settings.api_key
    if hmac.compare_digest(api_key, settings.api_key):
        default_ws = get_default_workspace_id(db)
        return Principal(
            workspace_id=default_ws,
            workspace_role="admin",
            is_admin=True,
            can_write=True,
            is_superadmin=True,
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
        workspace_id=client.workspace_id,
        workspace_role=None,
        client_id=client.id,
        is_admin=False,
        can_write=True,
        is_superadmin=False,
        role="client",
    )


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not isinstance(principal, Principal):
        from app.database import SessionLocal
        from app.services.tenancy import get_default_workspace_id
        with SessionLocal() as db:
            def_ws_id = get_default_workspace_id(db)
        return Principal(workspace_id=def_ws_id, is_admin=True, can_write=True, is_superadmin=True)
    if not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return principal


def require_write(principal: Principal = Depends(get_principal)) -> Principal:
    if not isinstance(principal, Principal):
        from app.database import SessionLocal
        from app.services.tenancy import get_default_workspace_id
        with SessionLocal() as db:
            def_ws_id = get_default_workspace_id(db)
        return Principal(workspace_id=def_ws_id, is_admin=True, can_write=True)
    if not principal.can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required.",
        )
    return principal


def require_superadmin(principal: Principal = Depends(get_principal)) -> Principal:
    if not isinstance(principal, Principal):
        from app.database import SessionLocal
        from app.services.tenancy import get_default_workspace_id
        with SessionLocal() as db:
            def_ws_id = get_default_workspace_id(db)
        return Principal(workspace_id=def_ws_id, is_admin=True, can_write=True, is_superadmin=True)
    if not principal.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required.",
        )
    return principal


verify_api_key = get_principal
