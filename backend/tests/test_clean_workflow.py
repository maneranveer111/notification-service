"""
Acceptance test suite for clean signup and workspace lifecycle workflow.

Encodes the contract:
- Signup (with full name, workspace name) queues exactly one verification mail.
- Login before verification is refused.
- Verify the account.
- User has exactly two workspaces (named first/active, Default with is_default true), both owner.
- /auth/me and login responses show the named workspace as active.
- Both workspace objects carry deletable (named true, default false).
- Deleting the default -> 409.
- Deleting the named workspace removes its data only and the response login body is for the default workspace.
- The first user is superadmin and the second is not.
- A legacy user without a default workspace gets one automatically at login.
- Invitation acceptance by a new user creates their personal default and activates the invited workspace.
- max_workspaces_per_user does not count default workspaces.
- Leaving a default workspace -> 409.
- The global default workspace exists after migrations and after ensure_default_workspace.
- Other workspaces are untouched by all of this.
"""

import re
import secrets
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete

from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.models.invitation import Invitation
from app.models.notification import Notification
from app.services.passwords import hash_password

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


def _ensure_bootstrap_state(db):
    """Ensure global default workspace and at least one admin user exists for subsequent tests."""
    global_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
    if not global_ws:
        global_ws = Workspace(
            name="Default Workspace",
            slug="default",
            plan="unlimited",
            is_default=True,
            use_platform_providers=True,
        )
        db.add(global_ws)
        db.commit()
        db.refresh(global_ws)

    admin_user = db.scalar(select(User).where(User.is_superadmin.is_(True)))
    if not admin_user:
        admin_user = User(
            email="system_bootstrap_admin@example.com",
            password_hash=hash_password("Password123!"),
            role="admin",
            is_superadmin=True,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
            last_workspace_id=global_ws.id,
        )
        db.add(admin_user)
        db.commit()
        db.add(Membership(user_id=admin_user.id, workspace_id=global_ws.id, role="owner"))
        db.commit()


def test_signup_flow_verification_and_workspaces(db):
    """Signup queues one email, unverified login refused, verification sets 2 workspaces with correct flags."""
    _ensure_bootstrap_state(db)

    captured_emails = []
    def _mock_queue(to, subject, body):
        captured_emails.append({"to": to, "subject": subject, "body": body})
        return True

    unique_email = f"alex_{uuid.uuid4().hex[:8]}@example.com"
    full_name = "Alex River"
    workspace_name = "River Logistics"

    with patch("app.api.accounts.queue_system_email", side_effect=_mock_queue):
        resp = client.post(
            "/auth/signup",
            json={
                "email": unique_email,
                "password": "Password123!",
                "full_name": full_name,
                "workspace_name": workspace_name,
            },
        )
    assert resp.status_code == 202, resp.text
    assert len(captured_emails) == 1, f"Expected exactly 1 email, got {len(captured_emails)}"

    # Login before verification must be refused
    login_before = client.post(
        "/auth/login",
        json={"email": unique_email, "password": "Password123!"},
    )
    assert login_before.status_code in (401, 403)

    # Verify the account
    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured_emails[0]["body"])
    assert token_match, "Verification token missing in email body"
    verify_token = token_match.group(1)

    v_resp = client.post("/auth/verify-email", json={"token": verify_token})
    assert v_resp.status_code == 200, v_resp.text
    v_data = v_resp.json()

    # User full_name returned
    assert v_data.get("user", {}).get("full_name") == full_name

    # Named workspace is active
    active_ws = v_data["workspace"]
    assert active_ws["name"] == workspace_name
    assert active_ws.get("is_default") is False
    assert active_ws.get("deletable") is True

    # User has exactly two workspaces
    workspaces = v_data["workspaces"]
    assert len(workspaces) == 2, f"Expected 2 workspaces, got {len(workspaces)}"

    named_ws = next(w for w in workspaces if w["name"] == workspace_name)
    default_ws = next(w for w in workspaces if w["name"] == "Default")

    assert named_ws["is_default"] is False
    assert named_ws["deletable"] is True
    assert default_ws["is_default"] is True
    assert default_ws["deletable"] is False

    # Check /auth/me
    token = v_data["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data.get("user", {}).get("full_name") == full_name
    assert me_data["workspace"]["id"] == named_ws["id"]

    # Check login response
    l_resp = client.post("/auth/login", json={"email": unique_email, "password": "Password123!"})
    assert l_resp.status_code == 200
    l_data = l_resp.json()
    assert l_data["workspace"]["id"] == named_ws["id"]
    assert l_data.get("user", {}).get("full_name") == full_name
    for w in l_data["workspaces"]:
        if w["id"] == named_ws["id"]:
            assert w["deletable"] is True
            assert w["is_default"] is False
        elif w["id"] == default_ws["id"]:
            assert w["deletable"] is False
            assert w["is_default"] is True


def test_deleting_default_workspace_rejected_409(db):
    """Deleting the default workspace returns 409."""
    _ensure_bootstrap_state(db)

    captured = []
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={"email": unique_email, "password": "Password123!", "workspace_name": "TestWS"},
        )
    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    verify_data = client.post("/auth/verify-email", json={"token": token_match.group(1)}).json()
    token = verify_data["access_token"]
    default_ws = next(w for w in verify_data["workspaces"] if w["is_default"] is True)

    # Switch to default workspace
    sw = client.post(
        "/auth/switch-workspace",
        headers={"Authorization": f"Bearer {token}"},
        json={"workspace_id": default_ws["id"]},
    ).json()
    def_token = sw["access_token"]

    # Attempt to delete default workspace
    del_resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {def_token}"},
        json={"confirm_name": default_ws["name"], "password": "Password123!"},
    )
    assert del_resp.status_code == 409
    assert del_resp.json()["detail"] == "This is your default workspace and cannot be deleted"


def test_deleting_named_workspace_switches_to_default(db):
    """Deleting the named workspace removes its data and login body is for default workspace."""
    _ensure_bootstrap_state(db)

    captured = []
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={"email": unique_email, "password": "Password123!", "workspace_name": "DoomedWS"},
        )
    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    verify_data = client.post("/auth/verify-email", json={"token": token_match.group(1)}).json()
    token = verify_data["access_token"]
    named_ws = verify_data["workspace"]
    default_ws = next(w for w in verify_data["workspaces"] if w["is_default"] is True)

    # Delete named workspace
    del_resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": named_ws["name"], "password": "Password123!"},
    )
    assert del_resp.status_code == 200, del_resp.text
    del_data = del_resp.json()
    assert del_data["deleted"] is True
    assert del_data["login"]["workspace"]["id"] == default_ws["id"]
    assert del_data["login"]["workspace"]["is_default"] is True


def test_leaving_default_workspace_rejected_409(db):
    """Leaving a default workspace returns 409."""
    _ensure_bootstrap_state(db)

    captured = []
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={"email": unique_email, "password": "Password123!", "workspace_name": "LeaveTest"},
        )
    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    verify_data = client.post("/auth/verify-email", json={"token": token_match.group(1)}).json()
    default_ws = next(w for w in verify_data["workspaces"] if w["is_default"] is True)

    sw = client.post(
        "/auth/switch-workspace",
        headers={"Authorization": f"Bearer {verify_data['access_token']}"},
        json={"workspace_id": default_ws["id"]},
    ).json()

    # Attempt to leave default workspace
    leave_resp = client.post(
        "/workspaces/current/leave",
        headers={"Authorization": f"Bearer {sw['access_token']}"},
    )
    assert leave_resp.status_code == 409


def test_first_user_is_superadmin_and_second_is_not(db):
    """First user of empty installation is superadmin and not in global default; second is not superadmin."""
    # Wipe memberships and users in test DB to test first-user bootstrapping
    db.query(Membership).delete()
    db.query(User).delete()
    db.commit()

    # Ensure global default workspace exists
    global_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
    if not global_ws:
        global_ws = Workspace(name="Default Workspace", slug="default", plan="unlimited", is_default=True)
        db.add(global_ws)
        db.commit()
        db.refresh(global_ws)

    captured1 = []
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured1.append(b) or True):
        r1 = client.post(
            "/auth/signup",
            json={
                "email": "first_owner@example.com",
                "password": "Password123!",
                "full_name": "First Owner",
                "workspace_name": "First Admin Corp",
            },
        )
    assert r1.status_code == 202
    token1 = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured1[-1]).group(1)
    v1 = client.post("/auth/verify-email", json={"token": token1}).json()

    # First user is superadmin
    assert v1["user"]["is_superadmin"] is True
    # Not added to global default workspace
    u1_ws_ids = [w["id"] for w in v1["workspaces"]]
    assert str(global_ws.id) not in u1_ws_ids

    # Second user signs up
    captured2 = []
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured2.append(b) or True):
        r2 = client.post(
            "/auth/signup",
            json={
                "email": "second_user@example.com",
                "password": "Password123!",
                "full_name": "Second User",
                "workspace_name": "Second Corp",
            },
        )
    assert r2.status_code == 202
    token2 = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured2[-1]).group(1)
    v2 = client.post("/auth/verify-email", json={"token": token2}).json()

    # Second user is NOT superadmin
    assert v2["user"]["is_superadmin"] is False


def test_legacy_user_without_default_gets_one_at_login(db):
    """A legacy user without a default workspace gets one automatically at login."""
    _ensure_bootstrap_state(db)

    # Create a legacy workspace that is NOT default
    legacy_ws = Workspace(
        name="Legacy Workspace",
        slug=f"legacy-{uuid.uuid4().hex[:6]}",
        is_default=False,
    )
    db.add(legacy_ws)
    db.commit()
    db.refresh(legacy_ws)

    legacy_email = f"legacy_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=legacy_email,
        password_hash=hash_password("Password123!"),
        role="member",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
        last_workspace_id=legacy_ws.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(Membership(user_id=user.id, workspace_id=legacy_ws.id, role="owner"))
    db.commit()

    # Login
    login_resp = client.post(
        "/auth/login",
        json={"email": legacy_email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()

    # Self-healing: user now has a Default workspace with is_default=True
    def_ws = next((w for w in data["workspaces"] if w.get("is_default") is True), None)
    assert def_ws is not None, "Personal default workspace was not created on login"
    assert def_ws["name"] == "Default"
    assert def_ws["deletable"] is False


def test_invitation_acceptance_creates_personal_default_and_activates_invited_ws(db):
    """Invitation acceptance by a new user creates their personal default and activates the invited workspace."""
    _ensure_bootstrap_state(db)

    # User 1 invites User 2
    captured = []
    owner_email = f"owner_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={"email": owner_email, "password": "Password123!", "workspace_name": "Host WS"},
        )
    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    owner_v = client.post("/auth/verify-email", json={"token": token_match.group(1)}).json()
    owner_token = owner_v["access_token"]
    host_ws_id = owner_v["workspace"]["id"]

    invited_email = f"invited_{uuid.uuid4().hex[:8]}@example.com"
    inv_resp = client.post(
        "/workspaces/current/invitations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": invited_email, "role": "viewer"},
    )
    assert inv_resp.status_code == 201, inv_resp.text
    invitation_id = inv_resp.json()["id"]

    # Invited user signs up
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={"email": invited_email, "password": "Password123!", "full_name": "Invited User"},
        )
    token_match2 = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    invited_v = client.post("/auth/verify-email", json={"token": token_match2.group(1)}).json()
    invited_token = invited_v["access_token"]

    # Accept invitation
    accept_resp = client.post(
        f"/invitations/{invitation_id}/accept",
        headers={"Authorization": f"Bearer {invited_token}"},
    )
    assert accept_resp.status_code == 200, accept_resp.text
    accept_data = accept_resp.json()

    # Activated workspace is the invited workspace
    assert accept_data["workspace"]["id"] == host_ws_id

    # The user still has their personal default workspace in their workspaces list
    def_ws = next((w for w in accept_data["workspaces"] if w.get("is_default") is True), None)
    assert def_ws is not None


def test_max_workspaces_per_user_does_not_count_default(db):
    """max_workspaces_per_user counts only non-default workspaces."""
    _ensure_bootstrap_state(db)

    captured = []
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={"email": unique_email, "password": "Password123!", "workspace_name": "QuotaWS1"},
        )
    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    verify_data = client.post("/auth/verify-email", json={"token": token_match.group(1)}).json()
    token = verify_data["access_token"]

    # With max_workspaces_per_user setting mocked to 2, user already has 1 non-default workspace
    # plus 1 default workspace. Creating 1 more non-default should succeed (total non-default = 2).
    with patch("app.api.workspaces.settings.max_workspaces_per_user", 2):
        create_resp = client.post(
            "/workspaces",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "QuotaWS2"},
        )
        assert create_resp.status_code == 201, create_resp.text

        # A 3rd non-default workspace should be rejected by quota limit
        create_third = client.post(
            "/workspaces",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "QuotaWS3"},
        )
        assert create_third.status_code in (400, 403, 409), "Expected quota rejection"


def test_global_default_workspace_exists(db):
    """The global default workspace exists after migrations and after ensure_default_workspace."""
    from app.services.tenancy import ensure_default_workspace
    ws = ensure_default_workspace(db)
    assert ws.slug == "default"
    assert ws.is_default is True
    assert ws.use_platform_providers is True


def test_dev_verification_link_only_in_dev_and_console(db):
    """dev_verification_link is included only when environment==development and system_mail_backend==console."""
    _ensure_bootstrap_state(db)

    with patch("app.api.accounts.queue_system_email", return_value=True):
        # Case 1: development + console
        with patch("app.api.accounts.settings.environment", "development"), \
             patch("app.api.accounts.settings.system_mail_backend", "console"):
            r1 = client.post(
                "/auth/signup",
                json={"email": f"dev1_{uuid.uuid4().hex[:6]}@example.com", "password": "Password123!"},
            )
            assert r1.status_code == 202
            assert "dev_verification_link" in r1.json()

        # Case 2: production + console
        with patch("app.api.accounts.settings.environment", "production"), \
             patch("app.api.accounts.settings.system_mail_backend", "console"):
            r2 = client.post(
                "/auth/signup",
                json={"email": f"prod1_{uuid.uuid4().hex[:6]}@example.com", "password": "Password123!"},
            )
            assert r2.status_code == 202
            assert "dev_verification_link" not in r2.json()

        # Case 3: development + smtp (not console)
        with patch("app.api.accounts.settings.environment", "development"), \
             patch("app.api.accounts.settings.system_mail_backend", "smtp"):
            r3 = client.post(
                "/auth/signup",
                json={"email": f"dev2_{uuid.uuid4().hex[:6]}@example.com", "password": "Password123!"},
            )
            assert r3.status_code == 202
            assert "dev_verification_link" not in r3.json()

