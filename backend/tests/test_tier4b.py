"""
Tier 4B: Accounts & Self-Service tests.
Tests signup, email verification, password reset, invitations, and change-password flows.
"""
import contextlib
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.invitation import Invitation
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.action_tokens import (
    make_invite_token,
    make_reset_token,
    make_verify_email_token,
)
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password
from app.services.tenancy import generate_workspace_slug
from app.tasks.notification_tasks import send_email_task, send_sms_task, send_webhook_task

client = TestClient(app)
settings = get_settings()
MASTER_HEADERS = {"X-API-Key": settings.api_key}


@pytest.fixture(autouse=True)
def reset_limiter_and_tasks():
    limiter.reset()
    with patch.object(send_email_task, "apply_async", return_value=MagicMock()) as m_email, \
         patch.object(send_sms_task, "apply_async", return_value=MagicMock()) as m_sms, \
         patch.object(send_webhook_task, "apply_async", return_value=MagicMock()) as m_wh:
        yield m_email, m_sms, m_wh
    limiter.reset()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helper: patch pydantic-settings (frozen) fields via object.__setattr__
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _settings_override(**kwargs):
    """
    Temporarily override fields on the cached pydantic-settings singleton.
    Works by bypassing the frozen model via object.__setattr__.
    All modules share the same @lru_cache instance, so one patch covers all.
    """
    obj = get_settings()
    saved = {k: getattr(obj, k) for k in kwargs}
    try:
        for k, v in kwargs.items():
            object.__setattr__(obj, k, v)
        yield
    finally:
        for k, v in saved.items():
            object.__setattr__(obj, k, v)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_verified_user(db, email, password="password123!", role="admin", ws_role="owner"):
    from app.services.tenancy import get_default_workspace_id
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        is_superadmin=False,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    try:
        ws_id = get_default_workspace_id(db)
        mem = Membership(user_id=user.id, workspace_id=ws_id, role=ws_role)
        db.add(mem)
    except Exception:
        pass
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user: User, workspace_id=None):
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=workspace_id,
    )
    return {"Authorization": f"Bearer {token}"}


def _create_workspace_for_user(db, user, role="owner"):
    ws = Workspace(
        name=f"WS {uuid.uuid4().hex[:6]}",
        slug=generate_workspace_slug("Test WS"),
        webhook_token=secrets.token_urlsafe(32),
    )
    db.add(ws)
    db.flush()
    mem = Membership(user_id=user.id, workspace_id=ws.id, role=role)
    db.add(mem)
    db.commit()
    db.refresh(ws)
    return ws


# ---------------------------------------------------------------------------
# 1. Signup tests
# ---------------------------------------------------------------------------

def test_signup_closed_returns_403():
    with _settings_override(signup_mode="closed"), \
         patch("app.api.accounts.queue_system_email"):
        resp = client.post("/auth/signup", json={"email": "x@example.com", "password": "password123"})
    assert resp.status_code == 403


def test_signup_invite_only_returns_403():
    with _settings_override(signup_mode="invite_only"), \
         patch("app.api.accounts.queue_system_email"):
        resp = client.post("/auth/signup", json={"email": "x@example.com", "password": "password123"})
    assert resp.status_code == 403


def test_signup_open_no_verification_creates_user(db):
    email = f"signup_noverify_{uuid.uuid4().hex[:8]}@example.com"
    with _settings_override(signup_mode="open", require_email_verification=False), \
         patch("app.api.accounts.queue_system_email") as mock_mail:
        resp = client.post("/auth/signup", json={"email": email, "password": "password123!"})
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    mock_mail.assert_not_called()

    user = db.scalar(select(User).where(User.email == email.lower()))
    assert user is not None
    assert user.email_verified_at is not None


def test_signup_open_with_verification_returns_202(db):
    email = f"signup_verify_{uuid.uuid4().hex[:8]}@example.com"
    with _settings_override(signup_mode="open", require_email_verification=True), \
         patch("app.api.accounts.queue_system_email") as mock_mail:
        resp = client.post("/auth/signup", json={"email": email, "password": "password123!"})
    assert resp.status_code == 202
    mock_mail.assert_called_once()

    user = db.scalar(select(User).where(User.email == email.lower()))
    assert user is not None
    assert user.email_verified_at is None


def test_signup_duplicate_with_verification_returns_202():
    """Duplicate email with verification enabled returns 202 (generic, no info leak)."""
    email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    with _settings_override(signup_mode="open", require_email_verification=True), \
         patch("app.api.accounts.queue_system_email"):
        client.post("/auth/signup", json={"email": email, "password": "password123!"})
        resp = client.post("/auth/signup", json={"email": email, "password": "password123!"})
    assert resp.status_code == 202


def test_signup_duplicate_no_verification_returns_409(db):
    email = f"dup2_{uuid.uuid4().hex[:8]}@example.com"
    with _settings_override(signup_mode="open", require_email_verification=False), \
         patch("app.api.accounts.queue_system_email"):
        client.post("/auth/signup", json={"email": email, "password": "password123!"})
        resp = client.post("/auth/signup", json={"email": email, "password": "password123!"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 2. Email verification flow
# ---------------------------------------------------------------------------

def test_login_blocked_when_unverified(db):
    email = f"unverified_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("password123!"),
        role="viewer",
        is_active=True,
        email_verified_at=None,
    )
    db.add(user)
    db.commit()

    with _settings_override(require_email_verification=True):
        resp = client.post("/auth/login", json={"email": email, "password": "password123!"})
    assert resp.status_code == 403


def test_verify_email_token_allows_login(db):
    email = f"toverify_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("password123!"),
        role="viewer",
        is_active=True,
        email_verified_at=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = make_verify_email_token(user.id)
    resp = client.post("/auth/verify-email", json={"token": token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data

    db.refresh(user)
    assert user.email_verified_at is not None


def test_verify_email_bad_token_returns_400():
    resp = client.post("/auth/verify-email", json={"token": "notavalidtoken"})
    assert resp.status_code == 400


def test_verify_email_wrong_purpose_returns_400(db):
    email = f"wrongpurpose_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("password123!"),
        role="viewer",
        is_active=True,
        email_verified_at=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Pass a reset token where verify email is expected
    wrong_token = make_reset_token(user.id, user.password_hash)
    resp = client.post("/auth/verify-email", json={"token": wrong_token})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Resend verification
# ---------------------------------------------------------------------------

def test_resend_verification_always_202():
    resp = client.post(
        "/auth/resend-verification",
        json={"email": "nonexistent@example.com"},
    )
    assert resp.status_code == 202


def test_resend_verification_sends_email_for_unverified(db):
    email = f"resend_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("password123!"),
        role="viewer",
        is_active=True,
        email_verified_at=None,
    )
    db.add(user)
    db.commit()

    with patch("app.api.accounts.queue_system_email") as mock_mail, \
         patch("app.api.accounts.check_rate_limit", return_value=True):
        resp = client.post("/auth/resend-verification", json={"email": email})
    assert resp.status_code == 202
    mock_mail.assert_called_once()


def test_resend_verification_no_email_for_verified(db):
    email = f"resend_verified_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("password123!"),
        role="viewer",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()

    with patch("app.api.accounts.queue_system_email") as mock_mail, \
         patch("app.api.accounts.check_rate_limit", return_value=True):
        resp = client.post("/auth/resend-verification", json={"email": email})
    assert resp.status_code == 202
    mock_mail.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Forgot / Reset password
# ---------------------------------------------------------------------------

def test_forgot_password_always_202():
    resp = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 202


def test_forgot_password_sends_email(db):
    email = f"forgot_{uuid.uuid4().hex[:8]}@example.com"
    user = _create_verified_user(db, email)

    with patch("app.api.accounts.queue_system_email") as mock_mail, \
         patch("app.api.accounts.check_rate_limit", return_value=True):
        resp = client.post("/auth/forgot-password", json={"email": email})
    assert resp.status_code == 202
    mock_mail.assert_called_once()


def test_reset_password_works(db):
    email = f"reset_{uuid.uuid4().hex[:8]}@example.com"
    user = _create_verified_user(db, email, password="oldpassword!")

    reset_token = make_reset_token(user.id, user.password_hash)
    resp = client.post("/auth/reset-password", json={
        "token": reset_token,
        "new_password": "newpassword123!",
    })
    assert resp.status_code == 200
    assert resp.json()["message"] == "Password updated"


def test_reset_password_invalidates_old_token(db):
    email = f"reset2_{uuid.uuid4().hex[:8]}@example.com"
    user = _create_verified_user(db, email, password="oldpassword!")

    reset_token = make_reset_token(user.id, user.password_hash)
    client.post("/auth/reset-password", json={
        "token": reset_token,
        "new_password": "newpassword123!",
    })

    # Using same token again should fail (pwf no longer matches)
    resp2 = client.post("/auth/reset-password", json={
        "token": reset_token,
        "new_password": "anotherpassword!",
    })
    assert resp2.status_code == 400


def test_reset_password_invalidates_old_jwt(db):
    import time
    email = f"resetjwt_{uuid.uuid4().hex[:8]}@example.com"
    user = _create_verified_user(db, email)
    old_headers = _auth_headers(user)

    time.sleep(1)  # ensure iat < password_changed_at
    reset_token = make_reset_token(user.id, user.password_hash)
    client.post("/auth/reset-password", json={
        "token": reset_token,
        "new_password": "brandnewpassword!",
    })

    # Old JWT should now be rejected
    resp = client.get("/auth/me", headers=old_headers)
    assert resp.status_code == 401


def test_reset_password_bad_token_returns_400():
    resp = client.post("/auth/reset-password", json={
        "token": "not-a-real-token",
        "new_password": "newpassword123!",
    })
    assert resp.status_code == 400


def test_reset_password_marks_verified(db):
    email = f"reset_verify_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("oldpass123!"),
        role="viewer",
        is_active=True,
        email_verified_at=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    reset_token = make_reset_token(user.id, user.password_hash)
    resp = client.post("/auth/reset-password", json={
        "token": reset_token,
        "new_password": "newpassword123!",
    })
    assert resp.status_code == 200

    db.refresh(user)
    assert user.email_verified_at is not None


# ---------------------------------------------------------------------------
# 5. Change password
# ---------------------------------------------------------------------------

def test_change_password_wrong_current_returns_400(db):
    user = _create_verified_user(db, f"chpw_{uuid.uuid4().hex[:8]}@example.com")
    headers = _auth_headers(user)

    resp = client.post("/auth/change-password", headers=headers, json={
        "current_password": "wrongpassword!",
        "new_password": "newpassword123!",
    })
    assert resp.status_code == 400


def test_change_password_success_returns_new_token(db):
    user = _create_verified_user(db, f"chpw2_{uuid.uuid4().hex[:8]}@example.com", password="password123!")
    headers = _auth_headers(user)

    resp = client.post("/auth/change-password", headers=headers, json={
        "current_password": "password123!",
        "new_password": "brandnewpassword!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


def test_change_password_invalidates_old_jwt(db):
    import time
    user = _create_verified_user(db, f"chpw3_{uuid.uuid4().hex[:8]}@example.com", password="password123!")
    old_headers = _auth_headers(user)

    time.sleep(1)  # ensure iat < password_changed_at

    new_headers = _auth_headers(user)
    client.post("/auth/change-password", headers=new_headers, json={
        "current_password": "password123!",
        "new_password": "brandnewpassword!",
    })

    # Old token issued before password change should be rejected
    resp = client.get("/auth/me", headers=old_headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 6. Invitation CRUD
# ---------------------------------------------------------------------------

def test_create_invitation_as_admin(db):
    user = _create_verified_user(db, f"inv_admin_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")
    headers = _auth_headers(user, workspace_id=ws.id)
    target_email = f"invitee_{uuid.uuid4().hex[:8]}@example.com"

    with patch("app.api.invitations.queue_system_email"):
        resp = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email, "role": "viewer"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == target_email
    assert data["status"] == "pending"


def test_create_invitation_as_viewer_returns_403(db):
    owner = _create_verified_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, owner, role="owner")

    viewer = User(
        email=f"viewer_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password!"),
        role="viewer",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(viewer)
    db.flush()
    db.add(Membership(user_id=viewer.id, workspace_id=ws.id, role="viewer"))
    db.commit()
    db.refresh(viewer)

    headers = _auth_headers(viewer, workspace_id=ws.id)
    with patch("app.api.invitations.queue_system_email"):
        resp = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": "someone@example.com", "role": "viewer"},
        )
    assert resp.status_code == 403


def test_create_invitation_owner_role_returns_422(db):
    user = _create_verified_user(db, f"inv_owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")
    headers = _auth_headers(user, workspace_id=ws.id)

    with patch("app.api.invitations.queue_system_email"):
        resp = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": "someone@example.com", "role": "owner"},
        )
    assert resp.status_code == 422


def test_create_invitation_duplicate_pending_returns_409(db):
    user = _create_verified_user(db, f"inv_dup_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")
    headers = _auth_headers(user, workspace_id=ws.id)
    target_email = f"invitee_dup_{uuid.uuid4().hex[:8]}@example.com"

    with patch("app.api.invitations.queue_system_email"):
        client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email, "role": "viewer"},
        )
        resp = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email, "role": "viewer"},
        )
    assert resp.status_code == 409


def test_create_invitation_existing_member_returns_409(db):
    user = _create_verified_user(db, f"inv_mem_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")
    headers = _auth_headers(user, workspace_id=ws.id)

    # Create a member
    member = User(
        email=f"existmember_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password!"),
        role="viewer",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(member)
    db.flush()
    db.add(Membership(user_id=member.id, workspace_id=ws.id, role="viewer"))
    db.commit()

    with patch("app.api.invitations.queue_system_email"):
        resp = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": member.email, "role": "viewer"},
        )
    assert resp.status_code == 409


def test_list_invitations(db):
    user = _create_verified_user(db, f"listinv_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")
    headers = _auth_headers(user, workspace_id=ws.id)
    target_email = f"listee_{uuid.uuid4().hex[:8]}@example.com"

    with patch("app.api.invitations.queue_system_email"):
        client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email, "role": "viewer"},
        )
        resp = client.get("/workspaces/current/invitations", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(inv["email"] == target_email for inv in data)


def test_revoke_invitation(db):
    user = _create_verified_user(db, f"revoke_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")
    headers = _auth_headers(user, workspace_id=ws.id)
    target_email = f"revokee_{uuid.uuid4().hex[:8]}@example.com"

    with patch("app.api.invitations.queue_system_email"):
        create_resp = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email, "role": "viewer"},
        )
        inv_id = create_resp.json()["id"]
        resp = client.delete(f"/workspaces/current/invitations/{inv_id}", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


def test_revoke_invitation_cross_workspace_returns_404(db):
    user1 = _create_verified_user(db, f"cross1_{uuid.uuid4().hex[:8]}@example.com")
    user2 = _create_verified_user(db, f"cross2_{uuid.uuid4().hex[:8]}@example.com")
    ws1 = _create_workspace_for_user(db, user1, role="owner")
    ws2 = _create_workspace_for_user(db, user2, role="owner")

    headers1 = _auth_headers(user1, workspace_id=ws1.id)
    headers2 = _auth_headers(user2, workspace_id=ws2.id)

    target_email = f"cross_inv_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.invitations.queue_system_email"):
        create_resp = client.post(
            "/workspaces/current/invitations",
            headers=headers1,
            json={"email": target_email, "role": "viewer"},
        )
        inv_id = create_resp.json()["id"]

        # user2 tries to delete user1's invitation
        resp = client.delete(f"/workspaces/current/invitations/{inv_id}", headers=headers2)
    assert resp.status_code == 404


def test_resend_invitation(db):
    user = _create_verified_user(db, f"resend_inv_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")
    headers = _auth_headers(user, workspace_id=ws.id)
    target_email = f"resendee_{uuid.uuid4().hex[:8]}@example.com"

    with patch("app.api.invitations.queue_system_email") as mock_mail:
        create_resp = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email, "role": "viewer"},
        )
        inv_id = create_resp.json()["id"]
        resp = client.post(f"/workspaces/current/invitations/{inv_id}/resend", headers=headers)

    assert resp.status_code == 200
    assert mock_mail.call_count == 2  # once on create, once on resend


# ---------------------------------------------------------------------------
# 7. Invitation info endpoint
# ---------------------------------------------------------------------------

def test_invitation_info_valid_token(db):
    user = _create_verified_user(db, f"info_host_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")

    inv_email = f"invinfo_{uuid.uuid4().hex[:8]}@example.com"
    invitation = Invitation(
        workspace_id=ws.id,
        email=inv_email,
        role="viewer",
        invited_by=user.id,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    resp = client.get(f"/auth/invitation-info?token={token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == inv_email
    assert data["role"] == "viewer"
    assert data["user_exists"] is False


def test_invitation_info_expired_returns_400(db):
    user = _create_verified_user(db, f"info_exp_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, user, role="owner")

    inv_email = f"expinfo_{uuid.uuid4().hex[:8]}@example.com"
    invitation = Invitation(
        workspace_id=ws.id,
        email=inv_email,
        role="viewer",
        invited_by=user.id,
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # already expired
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    resp = client.get(f"/auth/invitation-info?token={token}")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 8. Accept invitation
# ---------------------------------------------------------------------------

def test_accept_invitation_new_user(db):
    host = _create_verified_user(db, f"accept_host_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, host, role="owner")

    inv_email = f"newacceptee_{uuid.uuid4().hex[:8]}@example.com"
    invitation = Invitation(
        workspace_id=ws.id,
        email=inv_email,
        role="viewer",
        invited_by=host.id,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    resp = client.post("/auth/accept-invitation", json={
        "token": token,
        "password": "newpassword123!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data

    # User should be verified
    new_user = db.scalar(select(User).where(User.email == inv_email.lower()))
    assert new_user is not None
    assert new_user.email_verified_at is not None

    # Invitation should be accepted
    db.refresh(invitation)
    assert invitation.status == "accepted"


def test_accept_invitation_second_use_fails(db):
    host = _create_verified_user(db, f"host2_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, host, role="owner")

    inv_email = f"newacceptee2_{uuid.uuid4().hex[:8]}@example.com"
    invitation = Invitation(
        workspace_id=ws.id,
        email=inv_email,
        role="viewer",
        invited_by=host.id,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    client.post("/auth/accept-invitation", json={"token": token, "password": "newpassword123!"})

    # Second use of same token
    resp2 = client.post("/auth/accept-invitation", json={"token": token, "password": "newpassword123!"})
    assert resp2.status_code == 400


def test_accept_invitation_existing_user_no_auth_returns_401(db):
    host = _create_verified_user(db, f"host3_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, host, role="owner")
    existing = _create_verified_user(db, f"existing_{uuid.uuid4().hex[:8]}@example.com")

    invitation = Invitation(
        workspace_id=ws.id,
        email=existing.email,
        role="viewer",
        invited_by=host.id,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    # No auth header - existing user is required to log in
    resp = client.post("/auth/accept-invitation", json={"token": token})
    assert resp.status_code == 401


def test_accept_invitation_wrong_user_returns_403(db):
    host = _create_verified_user(db, f"host4_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, host, role="owner")
    target = _create_verified_user(db, f"target_{uuid.uuid4().hex[:8]}@example.com")
    wrong_user = _create_verified_user(db, f"wronguser_{uuid.uuid4().hex[:8]}@example.com")

    invitation = Invitation(
        workspace_id=ws.id,
        email=target.email,
        role="viewer",
        invited_by=host.id,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    # Authenticate as wrong user
    wrong_headers = _auth_headers(wrong_user, workspace_id=ws.id)
    resp = client.post("/auth/accept-invitation", headers=wrong_headers, json={"token": token})
    assert resp.status_code == 403


def test_accept_invitation_correct_existing_user(db):
    host = _create_verified_user(db, f"host5_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, host, role="owner")
    target = _create_verified_user(db, f"target2_{uuid.uuid4().hex[:8]}@example.com")

    invitation = Invitation(
        workspace_id=ws.id,
        email=target.email,
        role="viewer",
        invited_by=host.id,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    # Authenticate as the target user (different workspace context is fine)
    target_headers = _auth_headers(target)
    resp = client.post("/auth/accept-invitation", headers=target_headers, json={"token": token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


def test_accept_invitation_already_member_returns_409(db):
    host = _create_verified_user(db, f"host6_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, host, role="owner")
    target = _create_verified_user(db, f"target3_{uuid.uuid4().hex[:8]}@example.com")

    # Add target to workspace
    db.add(Membership(user_id=target.id, workspace_id=ws.id, role="viewer"))
    db.commit()

    invitation = Invitation(
        workspace_id=ws.id,
        email=target.email,
        role="viewer",
        invited_by=host.id,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    target_headers = _auth_headers(target)
    resp = client.post("/auth/accept-invitation", headers=target_headers, json={"token": token})
    assert resp.status_code == 409


def test_accept_revoked_invitation_returns_400(db):
    host = _create_verified_user(db, f"host7_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace_for_user(db, host, role="owner")

    invitation = Invitation(
        workspace_id=ws.id,
        email=f"revoked_{uuid.uuid4().hex[:8]}@example.com",
        role="viewer",
        invited_by=host.id,
        status="revoked",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    token = make_invite_token(invitation.id)
    resp = client.post("/auth/accept-invitation", json={"token": token, "password": "password123!"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 9. System mail backend
# ---------------------------------------------------------------------------

def test_console_mail_logs_info(caplog):
    import logging
    from app.tasks.system_tasks import send_system_email_task

    with _settings_override(system_mail_backend="console"):
        with caplog.at_level(logging.INFO, logger="app.tasks.system_tasks"):
            send_system_email_task.run("test@example.com", "Subject", "Body text")
    assert any("CONSOLE MAIL" in r.message for r in caplog.records)


def test_provider_mail_does_not_log_body(caplog):
    import logging
    from app.services.errors import PermanentError
    from app.tasks.system_tasks import send_system_email_task

    with patch("app.tasks.system_tasks.email_service.send_email", side_effect=PermanentError("fail")), \
         _settings_override(system_mail_backend="provider"):
        with caplog.at_level(logging.ERROR, logger="app.tasks.system_tasks"):
            with pytest.raises(PermanentError):
                send_system_email_task.run("test@example.com", "Subject", "Secret body")
    for record in caplog.records:
        assert "Secret body" not in record.getMessage()
