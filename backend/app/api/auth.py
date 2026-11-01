from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.schemas.auth import AuthMeResponse, LoginRequest, TokenResponse, UserAuthInfo, WorkspaceInfo
from app.security import Principal, get_user_principal
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

    # Find workspace membership
    membership = None
    if user.last_workspace_id:
        membership = db.get(Membership, (user.id, user.last_workspace_id))
    if not membership:
        membership = db.execute(
            select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at.asc())
        ).scalars().first()

    workspace_id = membership.workspace_id if membership else None
    workspace_info = None
    if membership:
        ws = db.get(Workspace, membership.workspace_id)
        if ws:
            workspace_info = WorkspaceInfo(id=ws.id, name=ws.name, slug=ws.slug, role=membership.role)

    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=workspace_id,
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
        workspace=workspace_info,
        is_superadmin=user.is_superadmin,
    )


@router.get("/me", response_model=AuthMeResponse)
def get_current_user_info(principal: Principal = Depends(get_user_principal), db: Session = Depends(get_db)):
    workspace_info = None
    workspaces = []

    if principal.user_id:
        # Current workspace
        if principal.workspace_id:
            ws = db.get(Workspace, principal.workspace_id)
            if ws and principal.workspace_role:
                workspace_info = WorkspaceInfo(
                    id=ws.id, name=ws.name, slug=ws.slug, role=principal.workspace_role
                )

        # All workspaces
        memberships = db.execute(
            select(Membership).where(Membership.user_id == principal.user_id)
        ).scalars().all()
        for m in memberships:
            ws = db.get(Workspace, m.workspace_id)
            if ws:
                workspaces.append(WorkspaceInfo(id=ws.id, name=ws.name, slug=ws.slug, role=m.role))

    return AuthMeResponse(
        id=principal.user_id,
        email=principal.email,
        role=principal.role or "user",
        can_write=principal.can_write,
        is_admin=principal.is_admin,
        is_superadmin=principal.is_superadmin,
        workspace=workspace_info,
        workspaces=workspaces,
    )
