from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.invitation import Invitation
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.schemas.auth import UserAuthInfo, WorkspaceInfo
from app.services.tenancy import ensure_personal_default_workspace
from app.security import Principal, get_user_principal, require_admin
from app.services.account_emails import invitation_email
from app.services.action_tokens import make_invite_token
from app.services.plans import get_plan
from app.services.system_mail import queue_system_email

router = APIRouter(
    prefix="/workspaces/current/invitations",
    tags=["Invitations"],
    dependencies=[Depends(require_admin)],
)
settings = get_settings()


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = Field(..., pattern="^(admin|viewer)$")


class InvitationRead(BaseModel):
    id: UUID
    workspace_id: UUID
    email: str
    role: str
    invited_by: UUID
    invited_by_email: str | None = None
    status: str
    expires_at: datetime
    created_at: datetime
    accepted_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


@router.post("", response_model=InvitationRead, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active workspace")

    ws = db.get(Workspace, principal.workspace_id)
    plan = get_plan(ws.plan if ws else "free")
    members_limit = plan.get("members")
    if members_limit is not None:
        members_count = (
            db.scalar(
                select(func.count(Membership.user_id)).where(
                    Membership.workspace_id == principal.workspace_id
                )
            )
            or 0
        )
        pending_count = (
            db.scalar(
                select(func.count(Invitation.id)).where(
                    Invitation.workspace_id == principal.workspace_id,
                    Invitation.status == "pending",
                )
            )
            or 0
        )
        if (members_count + pending_count) >= members_limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "detail": f"Member limit reached for {ws.plan if ws else 'free'} plan ({members_limit})",
                    "code": "plan_limit",
                    "resource": "members",
                    "limit": members_limit,
                },
            )

    target_email = payload.email.strip().lower()

    # Role check: only admin or viewer allowed
    if payload.role not in ("admin", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Role must be either 'admin' or 'viewer'",
        )

    # Check if target email is already a member
    target_user = db.scalar(select(User).where(User.email == target_email))
    if target_user:
        existing_membership = db.get(Membership, (target_user.id, principal.workspace_id))
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this workspace",
            )

    now = datetime.now(timezone.utc)

    # Check for existing pending invitation
    existing_inv = db.scalar(
        select(Invitation).where(
            Invitation.workspace_id == principal.workspace_id,
            func.lower(func.trim(Invitation.email)) == target_email,
            Invitation.status == "pending",
        )
    )
    if existing_inv:
        if existing_inv.expires_at <= now:
            existing_inv.status = "expired"
            db.commit()
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An invitation is already pending for this email",
            )

    invitation = Invitation(
        workspace_id=principal.workspace_id,
        email=target_email,
        role=payload.role,
        invited_by=principal.user_id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    link = f"{settings.frontend_public_url}/accept-invite?token={token}"
    ws = db.get(Workspace, principal.workspace_id)
    ws_name = ws.name if ws else "Workspace"

    subject, body = invitation_email(
        workspace_name=ws_name,
        inviter_email=principal.email or "An administrator",
        role=payload.role,
        link=link,
    )
    if not queue_system_email(to=target_email, subject=subject, body=body):
        # The invitation is already committed (pending) and is intentionally NOT
        # rolled back, so the existing resend workflow can recover. Return a safe
        # 503 without revealing internal details.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Invitation saved, but the email could not be sent. "
                          "Resend it later to deliver the invite."
            },
        )

    return InvitationRead(
        id=invitation.id,
        workspace_id=invitation.workspace_id,
        email=invitation.email,
        role=invitation.role,
        invited_by=invitation.invited_by,
        invited_by_email=principal.email,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
    )


@router.get("", response_model=list[InvitationRead])
def list_invitations(
    status: str | None = None,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    # Transition expired pending invitations to "expired"
    expired_invs = db.execute(
        select(Invitation).where(
            Invitation.workspace_id == principal.workspace_id,
            Invitation.status == "pending",
            Invitation.expires_at <= now,
        )
    ).scalars().all()
    if expired_invs:
        for inv in expired_invs:
            inv.status = "expired"
        db.commit()

    query = select(Invitation).where(Invitation.workspace_id == principal.workspace_id)
    if status:
        query = query.where(Invitation.status == status)
    invitations = db.execute(
        query.order_by(Invitation.created_at.desc())
    ).scalars().all()

    result = []
    for inv in invitations:
        inviter = db.get(User, inv.invited_by)
        result.append(
            InvitationRead(
                id=inv.id,
                workspace_id=inv.workspace_id,
                email=inv.email,
                role=inv.role,
                invited_by=inv.invited_by,
                invited_by_email=inviter.email if inviter else None,
                status=inv.status,
                expires_at=inv.expires_at,
                created_at=inv.created_at,
                accepted_at=inv.accepted_at,
            )
        )
    return result


@router.post("/{id}/resend", response_model=InvitationRead)
def resend_invitation(
    id: UUID,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    invitation = db.get(Invitation, id)
    if not invitation or invitation.workspace_id != principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.status not in ("pending", "expired"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending invitations can be resent",
        )

    now = datetime.now(timezone.utc)
    invitation.status = "pending"
    invitation.expires_at = now + timedelta(days=7)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    link = f"{settings.frontend_public_url}/accept-invite?token={token}"
    ws = db.get(Workspace, principal.workspace_id)
    ws_name = ws.name if ws else "Workspace"

    subject, body = invitation_email(
        workspace_name=ws_name,
        inviter_email=principal.email or "An administrator",
        role=invitation.role,
        link=link,
    )
    if not queue_system_email(to=invitation.email, subject=subject, body=body):
        # The invitation is already committed (pending) and is intentionally NOT
        # rolled back, so the existing resend workflow can recover.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "The invitation email could not be sent. "
                          "Resend it later to deliver the invite."
            },
        )

    inviter = db.get(User, invitation.invited_by)
    return InvitationRead(
        id=invitation.id,
        workspace_id=invitation.workspace_id,
        email=invitation.email,
        role=invitation.role,
        invited_by=invitation.invited_by,
        invited_by_email=inviter.email if inviter else None,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
    )


@router.delete("/{id}", response_model=InvitationRead)
def revoke_invitation(
    id: UUID,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    invitation = db.get(Invitation, id)
    if not invitation or invitation.workspace_id != principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending invitations can be revoked",
        )

    invitation.status = "revoked"
    db.commit()
    db.refresh(invitation)

    inviter = db.get(User, invitation.invited_by)
    return InvitationRead(
        id=invitation.id,
        workspace_id=invitation.workspace_id,
        email=invitation.email,
        role=invitation.role,
        invited_by=invitation.invited_by,
        invited_by_email=inviter.email if inviter else None,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
    )


# ---------------------------------------------------------------------------
# In-app user invitations (Inbox)
# ---------------------------------------------------------------------------

user_invitations_router = APIRouter(
    prefix="/invitations",
    tags=["User Invitations"],
)


class UserInvitationRead(BaseModel):
    id: UUID
    workspace_id: UUID
    workspace_name: str
    role: str
    status: str
    invited_by_email: str | None = None
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AcceptInvitationResponse(BaseModel):
    message: str = "Invitation accepted"
    id: UUID
    workspace_id: UUID
    workspace_name: str
    role: str
    status: str
    workspace: WorkspaceInfo | None = None
    workspaces: list[WorkspaceInfo] = []
    user: UserAuthInfo | None = None


class DeclineInvitationResponse(BaseModel):
    message: str = "Invitation declined"
    id: UUID
    status: str


@user_invitations_router.get("", response_model=list[UserInvitationRead])
def list_user_invitations(
    principal: Principal = Depends(get_user_principal),
    db: Session = Depends(get_db),
):
    if not principal.user_id or not principal.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user_email = principal.email.strip().lower()
    now = datetime.now(timezone.utc)
    invitations = db.execute(
        select(Invitation)
        .where(
            func.lower(func.trim(Invitation.email)) == user_email,
            Invitation.status == "pending",
            Invitation.expires_at > now,
        )
        .order_by(Invitation.created_at.desc())
    ).scalars().all()

    result: list[UserInvitationRead] = []
    for inv in invitations:
        ws = db.get(Workspace, inv.workspace_id)
        inviter = db.get(User, inv.invited_by)
        result.append(
            UserInvitationRead(
                id=inv.id,
                workspace_id=inv.workspace_id,
                workspace_name=ws.name if ws else "Workspace",
                role=inv.role,
                status=inv.status,
                invited_by_email=inviter.email if inviter else None,
                created_at=inv.created_at,
                expires_at=inv.expires_at,
            )
        )
    return result


@user_invitations_router.post("/{id}/accept", response_model=AcceptInvitationResponse)
def accept_user_invitation(
    id: UUID,
    principal: Principal = Depends(get_user_principal),
    db: Session = Depends(get_db),
):
    if not principal.user_id or not principal.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    invitation = db.get(Invitation, id)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if invitation.email.strip().lower() != principal.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invitation does not belong to the current user",
        )

    now = datetime.now(timezone.utc)
    if invitation.status == "expired" or (invitation.status == "pending" and invitation.expires_at <= now):
        invitation.status = "expired"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is no longer pending or has already been used",
        )

    existing_mem = db.get(Membership, (principal.user_id, invitation.workspace_id))
    if existing_mem:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already a member of this workspace",
        )

    # Create membership with specified role and mark invitation as accepted
    mem = Membership(
        user_id=principal.user_id,
        workspace_id=invitation.workspace_id,
        role=invitation.role,
    )
    db.add(mem)
    invitation.status = "accepted"
    invitation.accepted_at = now

    user = db.get(User, principal.user_id)
    if user:
        ensure_personal_default_workspace(db, user)
        user.last_workspace_id = invitation.workspace_id

    db.commit()
    db.refresh(mem)

    ws = db.get(Workspace, invitation.workspace_id)
    ws_info = None
    if ws:
        is_def = bool(getattr(ws, "is_default", False))
        ws_info = WorkspaceInfo(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            role=invitation.role,
            is_default=is_def,
            deletable=(invitation.role == "owner" and not is_def),
        )

    all_memberships = db.execute(
        select(Membership)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == principal.user_id)
        .order_by(Workspace.is_default.asc(), Membership.created_at.asc())
    ).scalars().all()
    workspaces_list: list[WorkspaceInfo] = []
    for m in all_memberships:
        wsi = db.get(Workspace, m.workspace_id)
        if wsi:
            is_def = bool(getattr(wsi, "is_default", False))
            workspaces_list.append(
                WorkspaceInfo(
                    id=wsi.id,
                    name=wsi.name,
                    slug=wsi.slug,
                    role=m.role,
                    is_default=is_def,
                    deletable=(m.role == "owner" and not is_def),
                )
            )

    user_info = None
    if user:
        user_info = UserAuthInfo(
            id=user.id,
            email=user.email,
            role=user.role,
            full_name=user.full_name,
            is_superadmin=user.is_superadmin,
        )

    return AcceptInvitationResponse(
        message="Invitation accepted",
        id=invitation.id,
        workspace_id=invitation.workspace_id,
        workspace_name=ws.name if ws else "Workspace",
        role=invitation.role,
        status="accepted",
        workspace=ws_info,
        workspaces=workspaces_list,
        user=user_info,
    )


@user_invitations_router.post("/{id}/decline", response_model=DeclineInvitationResponse)
def decline_user_invitation(
    id: UUID,
    principal: Principal = Depends(get_user_principal),
    db: Session = Depends(get_db),
):
    if not principal.user_id or not principal.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    invitation = db.get(Invitation, id)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if invitation.email.strip().lower() != principal.email.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invitation does not belong to the current user",
        )

    now = datetime.now(timezone.utc)
    if invitation.status == "expired" or (invitation.status == "pending" and invitation.expires_at <= now):
        invitation.status = "expired"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is no longer pending or has already been used",
        )

    invitation.status = "declined"
    db.commit()

    return DeclineInvitationResponse(
        message="Invitation declined",
        id=invitation.id,
        status="declined",
    )
