from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.invitation import Invitation
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.security import Principal, require_admin
from app.services.account_emails import invitation_email
from app.services.action_tokens import make_invite_token
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

    # Check for existing pending invitation
    existing_inv = db.scalar(
        select(Invitation).where(
            Invitation.workspace_id == principal.workspace_id,
            Invitation.email == target_email,
            Invitation.status == "pending",
        )
    )
    if existing_inv:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invitation is already pending for this email",
        )

    now = datetime.now(timezone.utc)
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
    queue_system_email(to=target_email, subject=subject, body=body)

    return invitation


@router.get("", response_model=list[InvitationRead])
def list_invitations(
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    invitations = db.execute(
        select(Invitation)
        .where(Invitation.workspace_id == principal.workspace_id)
        .order_by(Invitation.created_at.desc())
    ).scalars().all()
    return list(invitations)


@router.post("/{id}/resend", response_model=InvitationRead)
def resend_invitation(
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
            detail="Only pending invitations can be resent",
        )

    now = datetime.now(timezone.utc)
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
    queue_system_email(to=invitation.email, subject=subject, body=body)

    return invitation


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

    return invitation
