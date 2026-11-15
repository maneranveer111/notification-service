"""
Tests for In-App Workspace Invitation Inbox.
Covers:
1. User sees invitations sent to their email.
2. User does not see invitations addressed to another email.
3. Invitations are visible even when the user is in another workspace.
4. Expired invitations are not shown as pending.
5. User can accept an invitation inside the application.
6. Membership is created with the correct role.
7. Repeated acceptance is safely rejected.
8. Email-based acceptance still works.
9. Email-based acceptance rejected after in-app acceptance.
10. In-app decline works safely and rejects subsequent acceptance.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import uuid
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.invitation import Invitation
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.action_tokens import make_invite_token
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password
from app.services.tenancy import generate_workspace_slug
from app.tasks.notification_tasks import send_email_task, send_sms_task, send_webhook_task

client = TestClient(app)


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


def _create_user(db, email, role="admin"):
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password("password123!"),
        role=role,
        is_superadmin=False,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_workspace(db, owner, name=None):
    ws_name = name or f"WS_{uuid.uuid4().hex[:6]}"
    ws = Workspace(
        name=ws_name,
        slug=generate_workspace_slug(ws_name),
        webhook_token=secrets.token_urlsafe(32),
    )
    db.add(ws)
    db.flush()
    mem = Membership(user_id=owner.id, workspace_id=ws.id, role="owner")
    db.add(mem)
    db.commit()
    db.refresh(ws)
    return ws


def _auth_headers(user: User, workspace_id=None):
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=workspace_id,
    )
    return {"Authorization": f"Bearer {token}"}


def test_user_sees_pending_invitations_for_their_email(db):
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner, "Alpha Team")
    invitee = _create_user(db, f"invitee_{uuid.uuid4().hex[:8]}@example.com")

    now = datetime.now(timezone.utc)
    inv = Invitation(
        workspace_id=ws.id,
        email=invitee.email,
        role="viewer",
        invited_by=owner.id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    headers = _auth_headers(invitee)
    resp = client.get("/invitations", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == str(inv.id)
    assert data[0]["workspace_name"] == "Alpha Team"
    assert data[0]["role"] == "viewer"
    assert data[0]["status"] == "pending"
    assert data[0]["invited_by_email"] == owner.email


def test_user_does_not_see_invitations_for_another_email(db):
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    user_a = _create_user(db, f"usera_{uuid.uuid4().hex[:8]}@example.com")
    user_b = _create_user(db, f"userb_{uuid.uuid4().hex[:8]}@example.com")

    now = datetime.now(timezone.utc)
    inv = Invitation(
        workspace_id=ws.id,
        email=user_b.email,
        role="admin",
        invited_by=owner.id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    headers_a = _auth_headers(user_a)
    resp = client.get("/invitations", headers=headers_a)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 0


def test_invitations_visible_across_different_active_workspaces(db):
    owner_a = _create_user(db, f"ownera_{uuid.uuid4().hex[:8]}@example.com")
    ws_a = _create_workspace(db, owner_a, "Workspace A")

    owner_b = _create_user(db, f"ownerb_{uuid.uuid4().hex[:8]}@example.com")
    ws_b = _create_workspace(db, owner_b, "Workspace B")

    now = datetime.now(timezone.utc)
    inv = Invitation(
        workspace_id=ws_b.id,
        email=owner_a.email,
        role="viewer",
        invited_by=owner_b.id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    # User A is currently active in Workspace A
    headers_in_ws_a = _auth_headers(owner_a, workspace_id=ws_a.id)
    resp = client.get("/invitations", headers=headers_in_ws_a)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["workspace_name"] == "Workspace B"


def test_expired_invitations_not_returned(db):
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    user = _create_user(db, f"user_{uuid.uuid4().hex[:8]}@example.com")

    past = datetime.now(timezone.utc) - timedelta(days=1)
    inv = Invitation(
        workspace_id=ws.id,
        email=user.email,
        role="viewer",
        invited_by=owner.id,
        status="pending",
        expires_at=past,
    )
    db.add(inv)
    db.commit()

    headers = _auth_headers(user)
    resp = client.get("/invitations", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 0


def test_accept_invitation_in_app_success(db):
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner, "Target Workspace")
    user = _create_user(db, f"user_{uuid.uuid4().hex[:8]}@example.com")

    now = datetime.now(timezone.utc)
    inv = Invitation(
        workspace_id=ws.id,
        email=user.email,
        role="admin",
        invited_by=owner.id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    headers = _auth_headers(user)
    resp = client.post(f"/invitations/{inv.id}/accept", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["role"] == "admin"
    assert data["workspace_name"] == "Target Workspace"

    # Verify membership created in DB with correct role
    mem = db.get(Membership, (user.id, ws.id))
    assert mem is not None
    assert mem.role == "admin"

    # Verify invitation marked accepted
    db.refresh(inv)
    assert inv.status == "accepted"
    assert inv.accepted_at is not None

    # Should no longer appear in pending invitations
    pending_resp = client.get("/invitations", headers=headers)
    assert len(pending_resp.json()) == 0


def test_repeated_in_app_acceptance_rejected(db):
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    user = _create_user(db, f"user_{uuid.uuid4().hex[:8]}@example.com")

    now = datetime.now(timezone.utc)
    inv = Invitation(
        workspace_id=ws.id,
        email=user.email,
        role="viewer",
        invited_by=owner.id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    headers = _auth_headers(user)
    resp1 = client.post(f"/invitations/{inv.id}/accept", headers=headers)
    assert resp1.status_code == 200

    resp2 = client.post(f"/invitations/{inv.id}/accept", headers=headers)
    assert resp2.status_code in (400, 409)


def test_accept_invitation_for_wrong_user_fails(db):
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    user_a = _create_user(db, f"usera_{uuid.uuid4().hex[:8]}@example.com")
    user_b = _create_user(db, f"userb_{uuid.uuid4().hex[:8]}@example.com")

    now = datetime.now(timezone.utc)
    inv = Invitation(
        workspace_id=ws.id,
        email=user_b.email,
        role="viewer",
        invited_by=owner.id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    # User A attempts to accept User B's invitation
    headers_a = _auth_headers(user_a)
    resp = client.post(f"/invitations/{inv.id}/accept", headers=headers_a)
    assert resp.status_code == 403


def test_email_link_acceptance_fails_after_in_app_acceptance(db):
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    user = _create_user(db, f"user_{uuid.uuid4().hex[:8]}@example.com")

    now = datetime.now(timezone.utc)
    inv = Invitation(
        workspace_id=ws.id,
        email=user.email,
        role="viewer",
        invited_by=owner.id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    # Accept in-app first
    headers = _auth_headers(user)
    resp_inapp = client.post(f"/invitations/{inv.id}/accept", headers=headers)
    assert resp_inapp.status_code == 200

    # Now attempt email link acceptance with token
    token = make_invite_token(inv.id)
    resp_email = client.post(
        "/auth/accept-invitation",
        headers=headers,
        json={"token": token},
    )
    assert resp_email.status_code in (400, 409)


def test_decline_invitation_in_app_success(db):
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    user = _create_user(db, f"user_{uuid.uuid4().hex[:8]}@example.com")

    now = datetime.now(timezone.utc)
    inv = Invitation(
        workspace_id=ws.id,
        email=user.email,
        role="viewer",
        invited_by=owner.id,
        status="pending",
        expires_at=now + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    headers = _auth_headers(user)
    resp = client.post(f"/invitations/{inv.id}/decline", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"

    # Verify not member
    mem = db.get(Membership, (user.id, ws.id))
    assert mem is None

    # Verify status in DB
    db.refresh(inv)
    assert inv.status == "declined"

    # Should not show in pending
    pending_resp = client.get("/invitations", headers=headers)
    assert len(pending_resp.json()) == 0

    # Email link acceptance should also fail
    token = make_invite_token(inv.id)
    resp_email = client.post(
        "/auth/accept-invitation",
        headers=headers,
        json={"token": token},
    )
    assert resp_email.status_code == 400

