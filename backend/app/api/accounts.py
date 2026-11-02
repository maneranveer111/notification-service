from datetime import datetime, timezone
import hashlib
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.services.client_ip import client_ip
from app.models.invitation import Invitation
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.schemas.auth import TokenResponse, UserAuthInfo, WorkspaceInfo
from app.security import Principal, get_user_principal
from app.services.account_emails import reset_email, verification_email
from app.services.action_tokens import (
    decode_token,
    make_reset_token,
    make_verify_email_token,
)
from app.services.jwt_tokens import create_access_token, decode_access_token
from app.services.passwords import hash_password, verify_password
from app.services.rate_limit import check_rate_limit
from app.services.system_mail import queue_system_email
from app.services.tenancy import generate_workspace_slug, get_default_workspace_id

router = APIRouter(prefix="/auth", tags=["Accounts"])
settings = get_settings()


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    workspace_name: str | None = Field(default=None, max_length=100)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class InvitationInfoResponse(BaseModel):
    workspace_name: str
    email: str
    role: str
    user_exists: bool


def _build_token_response(user: User, db: Session, target_ws_id: UUID | None = None) -> TokenResponse:
    membership = None
    if target_ws_id:
        membership = db.get(Membership, (user.id, target_ws_id))
    if not membership and user.last_workspace_id:
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


@router.post("/signup")
@limiter.limit("5/hour", key_func=client_ip)
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    if settings.signup_mode == "closed":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signups are closed",
        )
    if settings.signup_mode == "invite_only":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signups are invite-only",
        )

    target_email = payload.email.strip().lower()

    # First user bootstrap with advisory lock to prevent race
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(727001);"))
    except Exception:
        pass
    user_count = db.scalar(select(func.count(User.id))) or 0
    if user_count == 0:
        default_ws_id = get_default_workspace_id(db)
        user = User(
            email=target_email,
            password_hash=hash_password(payload.password),
            role="admin",
            is_superadmin=True,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
            last_workspace_id=default_ws_id,
        )
        db.add(user)
        db.flush()

        mem = Membership(user_id=user.id, workspace_id=default_ws_id, role="owner")
        db.add(mem)
        db.commit()
        db.refresh(user)

        res = _build_token_response(user, db, default_ws_id)
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=res.model_dump(mode="json"))

    # Not first user
    existing_user = db.scalar(select(User).where(User.email == target_email))

    if settings.require_email_verification:
        if existing_user:
            hash_password(payload.password)  # Timing oracle mitigation
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={"message": "If this email is not registered, a verification link has been sent.", "email": target_email},
            )

        ws_name = (payload.workspace_name or f"{target_email.split('@')[0]}'s Workspace").strip()
        ws = Workspace(
            name=ws_name,
            slug=generate_workspace_slug(ws_name),
            webhook_token=secrets.token_urlsafe(32),
        )
        db.add(ws)
        db.flush()

        user = User(
            email=target_email,
            password_hash=hash_password(payload.password),
            role="admin",
            is_superadmin=False,
            is_active=True,
            email_verified_at=None,
            last_workspace_id=ws.id,
        )
        db.add(user)
        db.flush()

        mem = Membership(user_id=user.id, workspace_id=ws.id, role="owner")
        db.add(mem)
        db.commit()
        db.refresh(user)

        token = make_verify_email_token(user.id)
        link = f"{settings.frontend_public_url}/verify-email?token={token}"
        subject, body = verification_email(link)
        queue_system_email(target_email, subject, body)

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"message": "Verification email sent", "email": target_email},
        )
    else:
        if existing_user:
            hash_password(payload.password)  # Timing oracle mitigation
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        ws_name = (payload.workspace_name or f"{target_email.split('@')[0]}'s Workspace").strip()
        ws = Workspace(
            name=ws_name,
            slug=generate_workspace_slug(ws_name),
            webhook_token=secrets.token_urlsafe(32),
        )
        db.add(ws)
        db.flush()

        user = User(
            email=target_email,
            password_hash=hash_password(payload.password),
            role="admin",
            is_superadmin=False,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
            last_workspace_id=ws.id,
        )
        db.add(user)
        db.flush()

        mem = Membership(user_id=user.id, workspace_id=ws.id, role="owner")
        db.add(mem)
        db.commit()
        db.refresh(user)

        res = _build_token_response(user, db, ws.id)
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=res.model_dump(mode="json"))


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.token, expected_purpose="verify_email")
    try:
        user_id = UUID(data.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    if not user.email_verified_at:
        user.email_verified_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)

    return _build_token_response(user, db)


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/hour", key_func=client_ip)
def resend_verification(request: Request, payload: ResendVerificationRequest, db: Session = Depends(get_db)):
    target_email = payload.email.strip().lower()

    # Per-email rate limit: 1 per 60 seconds
    if check_rate_limit(f"resend:{target_email}", 1):
        user = db.scalar(select(User).where(User.email == target_email))
        if user and user.is_active and not user.email_verified_at:
            token = make_verify_email_token(user.id)
            link = f"{settings.frontend_public_url}/verify-email?token={token}"
            subject, body = verification_email(link)
            queue_system_email(user.email, subject, body)

    return {"message": "If this email is unverified, a verification link has been sent."}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour", key_func=client_ip)
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    target_email = payload.email.strip().lower()

    # Per-email rate limit: 1 per 60 seconds
    if check_rate_limit(f"forgot:{target_email}", 1):
        user = db.scalar(select(User).where(User.email == target_email))
        if user and user.is_active:
            token = make_reset_token(user.id, user.password_hash)
            link = f"{settings.frontend_public_url}/reset-password?token={token}"
            subject, body = reset_email(link)
            queue_system_email(user.email, subject, body)

    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.token, expected_purpose="reset_password")
    try:
        user_id = UUID(data.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    token_pwf = data.get("pwf")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    current_pwf = hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]
    if token_pwf != current_pwf:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has already been used or is invalid",
        )

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    if not user.email_verified_at:
        user.email_verified_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Password updated"}


@router.get("/invitation-info", response_model=InvitationInfoResponse)
@limiter.limit("20/minute", key_func=client_ip)
def get_invitation_info(request: Request, token: str, db: Session = Depends(get_db)):
    data = decode_token(token, expected_purpose="invite")
    try:
        inv_id = UUID(data.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    invitation = db.get(Invitation, inv_id)
    if not invitation or invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is invalid or has already been used",
        )

    if invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    ws = db.get(Workspace, invitation.workspace_id)
    existing_user = db.scalar(select(User).where(User.email == invitation.email))

    return InvitationInfoResponse(
        workspace_name=ws.name if ws else "Workspace",
        email=invitation.email,
        role=invitation.role,
        user_exists=bool(existing_user),
    )


@router.post("/accept-invitation", response_model=TokenResponse)
def accept_invitation(request: Request, payload: AcceptInvitationRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.token, expected_purpose="invite")
    try:
        inv_id = UUID(data.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token")

    invitation = db.get(Invitation, inv_id)
    if not invitation or invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is invalid or has already been used",
        )

    if invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token_str = auth_header[7:].strip()
        jwt_payload = decode_access_token(token_str)
        try:
            auth_user_id = UUID(jwt_payload.get("sub"))
        except (ValueError, TypeError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        current_user = db.get(User, auth_user_id)
        if not current_user or not current_user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        if current_user.email.lower() != invitation.email.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Logged in user email does not match invitation",
            )

        existing_membership = db.get(Membership, (current_user.id, invitation.workspace_id))
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Already a member of this workspace",
            )

        mem = Membership(user_id=current_user.id, workspace_id=invitation.workspace_id, role=invitation.role)
        db.add(mem)
        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(timezone.utc)
        current_user.last_workspace_id = invitation.workspace_id
        db.commit()
        db.refresh(current_user)

        return _build_token_response(current_user, db, invitation.workspace_id)
    else:
        existing_user = db.scalar(select(User).where(User.email == invitation.email.lower()))
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please log in to accept this invitation",
            )

        if not payload.password or len(payload.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password must be at least 8 characters",
            )

        new_user = User(
            email=invitation.email.lower(),
            password_hash=hash_password(payload.password),
            role="admin" if invitation.role == "admin" else "viewer",
            is_superadmin=False,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
            last_workspace_id=invitation.workspace_id,
        )
        db.add(new_user)
        db.flush()

        mem = Membership(user_id=new_user.id, workspace_id=invitation.workspace_id, role=invitation.role)
        db.add(mem)
        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(new_user)

        return _build_token_response(new_user, db, invitation.workspace_id)


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    payload: ChangePasswordRequest,
    principal: Principal = Depends(get_user_principal),
    db: Session = Depends(get_db),
):
    if not principal.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User authentication required")

    user = db.get(User, principal.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return _build_token_response(user, db, principal.workspace_id)

