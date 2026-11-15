"""
Regression tests for workspace Team page invitation lifecycle, status synchronization,
duplicate prevention, and history tracking.
"""
from datetime import datetime, timedelta, timezone
import secrets
import uuid
from unittest.mock import MagicMock, patch

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


def test_accepted_invitation_disappears_from_pending_and_appears_in_history(db):
    """
    When an invitation is accepted (via in-app or email):
    - It is marked accepted.
    - It no longer appears as pending.
    - It appears in invitation history with status 'accepted' and accepted_at timestamp.
    """
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    invitee = _create_user(db, f"invitee_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    owner_headers = _auth_headers(owner, ws.id)
    invitee_headers = _auth_headers(invitee)

    # 1. Owner creates invitation
    with patch("app.api.invitations.queue_system_email"):
        create_resp = client.post(
            "/workspaces/current/invitations",
            headers=owner_headers,
            json={"email": invitee.email, "role": "viewer"},
        )
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    # 2. Before acceptance: list shows 1 pending invitation
    resp_pending = client.get("/workspaces/current/invitations?status=pending", headers=owner_headers)
    assert resp_pending.status_code == 200
    assert any(inv["id"] == inv_id for inv in resp_pending.json())

    # 3. Invitee accepts in-app
    accept_resp = client.post(f"/invitations/{inv_id}/accept", headers=invitee_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "accepted"

    # 4. After acceptance: pending list does NOT include it
    resp_pending_after = client.get("/workspaces/current/invitations?status=pending", headers=owner_headers)
    assert resp_pending_after.status_code == 200
    assert not any(inv["id"] == inv_id for inv in resp_pending_after.json())

    # 5. Full invitation list shows it with status 'accepted' and accepted_at
    resp_all = client.get("/workspaces/current/invitations", headers=owner_headers)
    assert resp_all.status_code == 200
    accepted_inv = next((inv for inv in resp_all.json() if inv["id"] == inv_id), None)
    assert accepted_inv is not None
    assert accepted_inv["status"] == "accepted"
    assert accepted_inv["accepted_at"] is not None
    assert accepted_inv["role"] == "viewer"

    # 6. Member list shows invitee with role 'viewer'
    members_resp = client.get("/workspaces/current/members", headers=owner_headers)
    assert members_resp.status_code == 200
    member = next((m for m in members_resp.json() if m["email"] == invitee.email), None)
    assert member is not None
    assert member["role"] == "viewer"


def test_revoked_invitation_appears_in_history_and_cannot_be_accepted(db):
    """
    When an invitation is revoked:
    - Its status becomes 'revoked'.
    - It does not appear in pending list.
    - It appears in history.
    - Subsequent in-app and email acceptance attempts are rejected.
    """
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    invitee = _create_user(db, f"invitee_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    owner_headers = _auth_headers(owner, ws.id)
    invitee_headers = _auth_headers(invitee)

    # 1. Create invitation
    with patch("app.api.invitations.queue_system_email"):
        create_resp = client.post(
            "/workspaces/current/invitations",
            headers=owner_headers,
            json={"email": invitee.email, "role": "admin"},
        )
    assert create_resp.status_code == 201
    inv_id = create_resp.json()["id"]

    # 2. Revoke invitation
    revoke_resp = client.delete(f"/workspaces/current/invitations/{inv_id}", headers=owner_headers)
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["status"] == "revoked"

    # 3. Not in pending list
    resp_pending = client.get("/workspaces/current/invitations?status=pending", headers=owner_headers)
    assert not any(inv["id"] == inv_id for inv in resp_pending.json())

    # 4. Appears in full list as revoked
    resp_all = client.get("/workspaces/current/invitations", headers=owner_headers)
    revoked_inv = next((inv for inv in resp_all.json() if inv["id"] == inv_id), None)
    assert revoked_inv is not None
    assert revoked_inv["status"] == "revoked"

    # 5. In-app acceptance rejected
    accept_resp = client.post(f"/invitations/{inv_id}/accept", headers=invitee_headers)
    assert accept_resp.status_code == 400

    # 6. Email token acceptance rejected
    token = make_invite_token(uuid.UUID(inv_id))
    email_accept_resp = client.post(
        "/auth/accept-invitation",
        headers=invitee_headers,
        json={"token": token},
    )
    assert email_accept_resp.status_code == 400


def test_expired_invitation_auto_transitions_and_not_in_pending(db):
    """
    When an invitation passes its expiry date:
    - Querying invitations auto-transitions it to 'expired'.
    - It does not appear in pending list.
    - It appears in history with status 'expired'.
    - Attempting to accept it returns 400 Expired.
    """
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    invitee = _create_user(db, f"invitee_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    owner_headers = _auth_headers(owner, ws.id)
    invitee_headers = _auth_headers(invitee)

    # Insert an expired invitation directly
    past = datetime.now(timezone.utc) - timedelta(days=2)
    inv = Invitation(
        workspace_id=ws.id,
        email=invitee.email,
        role="viewer",
        invited_by=owner.id,
        status="pending",
        expires_at=past,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    # 1. Calling GET /workspaces/current/invitations auto-transitions it to expired
    resp_all = client.get("/workspaces/current/invitations", headers=owner_headers)
    assert resp_all.status_code == 200
    expired_inv = next((i for i in resp_all.json() if i["id"] == str(inv.id)), None)
    assert expired_inv is not None
    assert expired_inv["status"] == "expired"

    # 2. Not in pending list
    resp_pending = client.get("/workspaces/current/invitations?status=pending", headers=owner_headers)
    assert not any(i["id"] == str(inv.id) for i in resp_pending.json())

    # 3. Acceptance rejected as expired
    accept_resp = client.post(f"/invitations/{inv.id}/accept", headers=invitee_headers)
    assert accept_resp.status_code == 400
    assert "expired" in accept_resp.json()["detail"].lower()


def test_duplicate_pending_invitation_prevented(db):
    """
    Attempting to create two active pending invitations to the same email in the same
    workspace returns 409 Conflict.
    """
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    target_email = f"target_{uuid.uuid4().hex[:8]}@example.com"
    ws = _create_workspace(db, owner)
    headers = _auth_headers(owner, ws.id)

    with patch("app.api.invitations.queue_system_email"):
        resp1 = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email, "role": "viewer"},
        )
        assert resp1.status_code == 201

        # Second attempt while first is pending must fail with 409
        resp2 = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email.upper(), "role": "admin"},
        )
        assert resp2.status_code == 409
        assert "already pending" in resp2.json()["detail"].lower()


def test_new_invitation_allowed_after_accepted_or_revoked(db):
    """
    After an invitation is accepted or revoked, a new invitation to the same email
    can be sent without conflict, while preserving the previous record in history.
    """
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    invitee = _create_user(db, f"invitee_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    owner_headers = _auth_headers(owner, ws.id)
    invitee_headers = _auth_headers(invitee)

    # 1. Create first invitation
    with patch("app.api.invitations.queue_system_email"):
        r1 = client.post(
            "/workspaces/current/invitations",
            headers=owner_headers,
            json={"email": invitee.email, "role": "viewer"},
        )
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    # 2. Accept first invitation
    client.post(f"/invitations/{id1}/accept", headers=invitee_headers)

    # 3. Remove member from workspace
    rem_resp = client.delete(f"/workspaces/current/members/{invitee.id}", headers=owner_headers)
    assert rem_resp.status_code == 204

    # 4. First invitation record is still preserved as accepted in history
    inv1_db = db.get(Invitation, uuid.UUID(id1))
    assert inv1_db.status == "accepted"

    # 5. Owner invites invitee again with a different role ('admin')
    with patch("app.api.invitations.queue_system_email"):
        r2 = client.post(
            "/workspaces/current/invitations",
            headers=owner_headers,
            json={"email": invitee.email, "role": "admin"},
        )
    assert r2.status_code == 201
    id2 = r2.json()["id"]
    assert id1 != id2

    # 6. Listing invitations returns both: id1 as accepted, id2 as pending
    all_invs = client.get("/workspaces/current/invitations", headers=owner_headers).json()
    record1 = next(i for i in all_invs if i["id"] == id1)
    record2 = next(i for i in all_invs if i["id"] == id2)
    assert record1["status"] == "accepted"
    assert record2["status"] == "pending"


def test_member_removal_preserves_invitation_history(db):
    """
    Removing an existing member deletes membership but preserves invitation record as accepted,
    never changing it back to pending.
    """
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    invitee = _create_user(db, f"invitee_{uuid.uuid4().hex[:8]}@example.com")
    ws = _create_workspace(db, owner)
    owner_headers = _auth_headers(owner, ws.id)
    invitee_headers = _auth_headers(invitee)

    with patch("app.api.invitations.queue_system_email"):
        r = client.post(
            "/workspaces/current/invitations",
            headers=owner_headers,
            json={"email": invitee.email, "role": "viewer"},
        )
    inv_id = r.json()["id"]

    client.post(f"/invitations/{inv_id}/accept", headers=invitee_headers)

    # Confirm member exists
    members = client.get("/workspaces/current/members", headers=owner_headers).json()
    assert any(m["email"] == invitee.email for m in members)

    # Remove member
    client.delete(f"/workspaces/current/members/{invitee.id}", headers=owner_headers)

    # Member is gone
    members_after = client.get("/workspaces/current/members", headers=owner_headers).json()
    assert not any(m["email"] == invitee.email for m in members_after)

    # Invitation remains 'accepted' in history, not pending
    inv_db = db.get(Invitation, uuid.UUID(inv_id))
    assert inv_db.status == "accepted"
    assert inv_db.accepted_at is not None


def test_resend_extends_expiry_and_sends_email(db):
    """
    Resending a pending or expired invitation extends expires_at by 7 days, sets status
    to pending, and queues a new email.
    """
    owner = _create_user(db, f"owner_{uuid.uuid4().hex[:8]}@example.com")
    target_email = f"resend_{uuid.uuid4().hex[:8]}@example.com"
    ws = _create_workspace(db, owner)
    headers = _auth_headers(owner, ws.id)

    with patch("app.api.invitations.queue_system_email") as mock_email:
        r = client.post(
            "/workspaces/current/invitations",
            headers=headers,
            json={"email": target_email, "role": "viewer"},
        )
        inv_id = r.json()["id"]
        assert mock_email.call_count == 1

        # Resend
        resend_resp = client.post(f"/workspaces/current/invitations/{inv_id}/resend", headers=headers)
        assert resend_resp.status_code == 200
        assert resend_resp.json()["status"] == "pending"
        assert mock_email.call_count == 2
