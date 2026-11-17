from datetime import datetime, timezone
import hashlib
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
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
from app.services.captcha import verify_captcha
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
    full_name: str | None = Field(default=None, max_length=100)
    captcha_token: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr
    captcha_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    captcha_token: str | None = None


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

    all_memberships = db.execute(
        select(Membership).where(Membership.user_id == user.id)
    ).scalars().all()
    workspaces_list: list[WorkspaceInfo] = []
    for m in all_memberships:
        wsi = db.get(Workspace, m.workspace_id)
        if wsi:
            workspaces_list.append(WorkspaceInfo(id=wsi.id, name=wsi.name, slug=wsi.slug, role=m.role))

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
            full_name=user.full_name,
        ),
        workspace=workspace_info,
        is_superadmin=user.is_superadmin,
        workspaces=workspaces_list,
    )


@router.post("/signup")
@limiter.limit("5/hour", key_func=client_ip)
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    verify_captcha(request, payload.captcha_token)

    if settings.signup_mode == "closed":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signups are closed",
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

        # Optionally rename the default workspace (keep slug=default, plan=unlimited).
        ws_name = (payload.workspace_name or "").strip()
        if ws_name and 1 <= len(ws_name) <= 100:
            default_ws = db.get(Workspace, default_ws_id)
            if default_ws:
                default_ws.name = ws_name

        if settings.require_email_verification:
            verified_at: datetime | None = None
        else:
            verified_at = datetime.now(timezone.utc)

        user = User(
            email=target_email,
            password_hash=hash_password(payload.password),
            role="admin",
            is_superadmin=True,
            is_active=True,
            email_verified_at=verified_at,
            last_workspace_id=default_ws_id,
            full_name=(payload.full_name or '').strip() or None,
        )
        db.add(user)
        db.flush()

        mem = Membership(user_id=user.id, workspace_id=default_ws_id, role="owner")
        db.add(mem)
        db.commit()
        db.refresh(user)

        if settings.require_email_verification:
            # Do not mark the first owner verified and do not issue an access token
            # before verification. Send the verification email using the same secure
            # mechanism as regular signup. If enqueueing fails, return an honest
            # error (never claim the email was sent); the owner can recover via
            # /auth/resend-verification or by re-submitting signup (which routes to
            # the existing-unverified resend path).
            token = make_verify_email_token(user.id)
            link = f"{settings.frontend_public_url}/verify-email?token={token}"
            subject, body = verification_email(link)
            if queue_system_email(target_email, subject, body):
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"message": "Verification email sent", "email": target_email},
                )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "detail": "Account created, but the verification email could not be sent. "
                              "Request a new verification email to activate your account.",
                    "email": target_email,
                },
            )

        res = _build_token_response(user, db, default_ws_id)
        return JSONResponse(status_code=status.HTTP_201_CREATED, content=res.model_dump(mode="json"))

    if settings.signup_mode == "invite_only":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signups are invite-only",
        )

    # Not first user
    existing_user = db.scalar(
        select(User).where(func.lower(func.trim(User.email)) == target_email)
    )

    if existing_user:
        hash_password(payload.password)  # Timing oracle mitigation
        if existing_user.email_verified_at is not None:
            # Case 1: Existing verified account
            # Do not create another user, do not send verification email, direct to sign in
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )
        else:
            # Case 2: Existing unverified account
            # Reuse existing account, do not generate unlimited tokens
            if settings.require_email_verification:
                # Attempt a resend only when not rate-limited. A rate-limited
                # request returns the same vague acknowledgment (no email
                # enumeration, no misleading "sent" claim because no send was
                # attempted). Only an actual enqueue failure yields an error.
                attempted = False
                sent = False
                if check_rate_limit(f"resend:{target_email}", 1):
                    attempted = True
                    token = make_verify_email_token(existing_user.id)
                    link = f"{settings.frontend_public_url}/verify-email?token={token}"
                    subject, body = verification_email(link)
                    sent = queue_system_email(existing_user.email, subject, body)
                if not attempted or sent:
                    return JSONResponse(
                        status_code=status.HTTP_202_ACCEPTED,
                        content={
                            "message": "If this email is unverified, a verification link has been sent.",
                            "email": target_email,
                            "status": "pending_verification",
                        },
                    )
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"detail": "Could not send the verification email right now. Please try again later."},
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists.",
                )

    # Case 3: New email address
    try:
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
            email_verified_at=None if settings.require_email_verification else datetime.now(timezone.utc),
            last_workspace_id=ws.id,
            full_name=(payload.full_name or '').strip() or None,
        )
        db.add(user)
        db.flush()

        mem = Membership(user_id=user.id, workspace_id=ws.id, role="owner")
        db.add(mem)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        # Concurrency catch: user was created concurrently
        existing_user = db.scalar(
            select(User).where(func.lower(func.trim(User.email)) == target_email)
        )
        if existing_user:
            hash_password(payload.password)
            if existing_user.email_verified_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="An account with this email already exists.",
                )
            elif settings.require_email_verification:
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={
                        "message": "If this email is unverified, a verification link has been sent.",
                        "email": target_email,
                        "status": "pending_verification",
                    },
                )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    if settings.require_email_verification:
        token = make_verify_email_token(user.id)
        link = f"{settings.frontend_public_url}/verify-email?token={token}"
        subject, body = verification_email(link)
        if check_rate_limit(f"resend:{target_email}", 1):
            # Rate limiter permits: queue the verification email. Preserve the
            # existing 503 for an actual enqueue failure.
            if queue_system_email(target_email, subject, body):
                return JSONResponse(
                    status_code=status.HTTP_202_ACCEPTED,
                    content={"message": "Verification email sent", "email": target_email},
                )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Could not send the verification email right now. Please try again later."},
            )
        # Rate-limited: do not queue and do not claim an email was sent. Return a
        # vague anti-enumeration 202 (same conditional framing as the resend and
        # existing-unverified flows) so the rate-limit state is not revealed. The
        # user and workspace are NOT rolled back; the owner can recover via
        # /auth/resend-verification.
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "If this email is unverified, a verification link can be requested.",
                "email": target_email,
            },
        )
    else:
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
    verify_captcha(request, payload.captcha_token)
    target_email = payload.email.strip().lower()

    # Per-email rate limit: 1 per 60 seconds
    if check_rate_limit(f"resend:{target_email}", 1):
        user = db.scalar(select(User).where(func.lower(func.trim(User.email)) == target_email))
        if user and user.is_active and not user.email_verified_at:
            token = make_verify_email_token(user.id)
            link = f"{settings.frontend_public_url}/verify-email?token={token}"
            subject, body = verification_email(link)
            # Only an actual enqueue failure for a real unverified user yields an
            # honest error; the vague 202 is preserved for no-user / rate-limited /
            # already-verified cases to avoid email enumeration.
            if not queue_system_email(user.email, subject, body):
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"detail": "Could not send the verification email right now. Please try again later."},
                )

    return {"message": "If this email is unverified, a verification link has been sent."}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/hour", key_func=client_ip)
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    verify_captcha(request, payload.captcha_token)
    target_email = payload.email.strip().lower()

    # Per-email rate limit: 1 per 60 seconds
    if check_rate_limit(f"forgot:{target_email}", 1):
        user = db.scalar(select(User).where(func.lower(func.trim(User.email)) == target_email))
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
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.status == "expired" or (invitation.status == "pending" and invitation.expires_at <= datetime.now(timezone.utc)):
        invitation.status = "expired"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is invalid or has already been used",
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
    if not invitation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.status == "expired" or (invitation.status == "pending" and invitation.expires_at <= datetime.now(timezone.utc)):
        invitation.status = "expired"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is invalid or has already been used",
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

