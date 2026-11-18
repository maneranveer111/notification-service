import re
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.tenancy import get_default_workspace

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


def _ensure_bootstrap_state(db):
    """Ensure at least one user exists so subsequent signups use normal signup flow."""
    default_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
    if not default_ws:
        default_ws = Workspace(name="Default Workspace", slug="default", plan="unlimited")
        db.add(default_ws)
        db.commit()
        db.refresh(default_ws)

    first_user = db.scalar(select(User))
    if not first_user:
        from app.services.passwords import hash_password
        first_user = User(
            email="admin_system@example.com",
            password_hash=hash_password("Password123!"),
            role="admin",
            is_superadmin=True,
            is_active=True,
            last_workspace_id=default_ws.id,
        )
        db.add(first_user)
        db.commit()
        db.add(Membership(user_id=first_user.id, workspace_id=default_ws.id, role="owner"))
        db.commit()


def test_new_signup_creates_custom_and_default_workspace(db):
    """Scenario A: New signup creates custom workspace (active) and ensures Default Workspace exists."""
    _ensure_bootstrap_state(db)

    captured = []
    def _mock_queue(to, subject, body):
        captured.append({"to": to, "body": body})
        return True

    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=_mock_queue):
        resp = client.post(
            "/auth/signup",
            json={
                "email": unique_email,
                "password": "Password123!",
                "workspace_name": "Acme Innovations",
            },
        )
    assert resp.status_code == 202, resp.text

    # Extract verification token
    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1]["body"])
    assert token_match, "Verification token missing in email body"
    verify_token = token_match.group(1)

    # Verify email
    v_resp = client.post("/auth/verify-email", json={"token": verify_token})
    assert v_resp.status_code == 200, v_resp.text
    data = v_resp.json()

    # Active workspace must be the custom signup workspace
    assert data["workspace"]["name"] == "Acme Innovations"
    assert data["workspace"]["slug"] != "default"

    # Workspace selector list must contain both the custom workspace and Default Workspace
    ws_defaults = [w["is_default"] for w in data["workspaces"]]
    assert True in ws_defaults
    assert False in ws_defaults
    assert len(data["workspaces"]) == 2

    # Login and verify landing in the custom workspace
    l_resp = client.post(
        "/auth/login",
        json={"email": unique_email, "password": "Password123!"},
    )
    assert l_resp.status_code == 200, l_resp.text
    login_data = l_resp.json()
    assert login_data["workspace"]["name"] == "Acme Innovations"
    assert login_data["workspace"]["slug"] != "default"


def test_switch_between_custom_and_default_workspace(db):
    """Scenario B: Normal workspace switching between custom and default workspace."""
    _ensure_bootstrap_state(db)

    captured = []
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={
                "email": unique_email,
                "password": "Password123!",
                "workspace_name": "Beta Workspace",
            },
        )

    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    verify_data = client.post("/auth/verify-email", json={"token": token_match.group(1)}).json()

    custom_ws = verify_data["workspace"]
    default_ws = next(w for w in verify_data["workspaces"] if w["is_default"] is True)
    token = verify_data["access_token"]

    # Switch to Default Workspace
    sw_resp = client.post(
        "/auth/switch-workspace",
        headers={"Authorization": f"Bearer {token}"},
        json={"workspace_id": default_ws["id"]},
    )
    assert sw_resp.status_code == 200, sw_resp.text
    sw_data = sw_resp.json()
    assert sw_data["workspace"]["id"] == default_ws["id"]
    new_token = sw_data["access_token"]

    # Current workspace endpoint reflects Default Workspace
    curr_resp = client.get("/workspaces/current", headers={"Authorization": f"Bearer {new_token}"})
    assert curr_resp.status_code == 200
    assert curr_resp.json()["id"] == default_ws["id"]

    # Switch back to Custom Workspace
    sw_back = client.post(
        "/auth/switch-workspace",
        headers={"Authorization": f"Bearer {new_token}"},
        json={"workspace_id": custom_ws["id"]},
    )
    assert sw_back.status_code == 200
    assert sw_back.json()["workspace"]["id"] == custom_ws["id"]


def test_delete_custom_workspace_auto_switches_to_default_workspace(db):
    """Scenario C: Deleting custom workspace automatically switches user to existing Default Workspace."""
    _ensure_bootstrap_state(db)

    captured = []
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={
                "email": unique_email,
                "password": "Password123!",
                "workspace_name": "Disposable WS",
            },
        )

    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    verify_data = client.post("/auth/verify-email", json={"token": token_match.group(1)}).json()
    token = verify_data["access_token"]
    custom_ws = verify_data["workspace"]
    default_ws = next(w for w in verify_data["workspaces"] if w["is_default"] is True)

    # Delete custom workspace
    del_resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": custom_ws["name"], "password": "Password123!"},
    )
    assert del_resp.status_code == 200, del_resp.text
    del_data = del_resp.json()
    assert del_data["deleted"] is True
    assert del_data["login"] is not None

    # Switched automatically to Default Workspace
    switched_login = del_data["login"]
    assert switched_login["workspace"]["id"] == default_ws["id"]
    assert switched_login["workspace"]["is_default"] is True

    # User can continue using the application with the new token
    new_token = switched_login["access_token"]
    curr_resp = client.get("/workspaces/current", headers={"Authorization": f"Bearer {new_token}"})
    assert curr_resp.status_code == 200
    assert curr_resp.json()["id"] == default_ws["id"]


def test_protect_default_workspace_from_deletion(db):
    """Scenario D: Default Workspace cannot be deleted through API."""
    _ensure_bootstrap_state(db)

    captured = []
    unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    with patch("app.api.accounts.queue_system_email", side_effect=lambda to, s, b: captured.append(b) or True):
        client.post(
            "/auth/signup",
            json={
                "email": unique_email,
                "password": "Password123!",
                "workspace_name": "Sample WS",
            },
        )

    token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1])
    verify_data = client.post("/auth/verify-email", json={"token": token_match.group(1)}).json()
    default_ws = next(w for w in verify_data["workspaces"] if w["is_default"] is True)
    token = verify_data["access_token"]

    # Switch to Default Workspace
    sw_data = client.post(
        "/auth/switch-workspace",
        headers={"Authorization": f"Bearer {token}"},
        json={"workspace_id": default_ws["id"]},
    ).json()
    def_token = sw_data["access_token"]

    # Attempt deletion of Default Workspace
    del_resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {def_token}"},
        json={"confirm_name": default_ws["name"], "password": "Password123!"},
    )
    assert del_resp.status_code == 409
    assert "cannot be deleted" in del_resp.json()["detail"].lower()

    # Verify Default Workspace still exists
    def_ws_row = db.get(Workspace, default_ws["id"])
    assert def_ws_row is not None


def test_existing_users_continuity(db):
    """Scenario E: Existing users continue to work without disruption."""
    _ensure_bootstrap_state(db)

    from datetime import datetime, timezone
    from app.services.passwords import hash_password
    existing_email = f"existing_{uuid.uuid4().hex[:8]}@example.com"
    default_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
    user = User(
        email=existing_email,
        password_hash=hash_password("Password123!"),
        role="member",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
        last_workspace_id=default_ws.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(Membership(user_id=user.id, workspace_id=default_ws.id, role="member"))
    db.commit()

    # Existing user logs in
    login_resp = client.post(
        "/auth/login",
        json={"email": existing_email, "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text
    data = login_resp.json()
    assert "access_token" in data
    assert data["workspace"] is not None
    assert data["workspace"]["id"] == str(default_ws.id)
    token = data["access_token"]

    # Existing user can access current workspace and protected endpoints
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == existing_email

    curr_resp = client.get("/workspaces/current", headers={"Authorization": f"Bearer {token}"})
    assert curr_resp.status_code == 200
    assert curr_resp.json()["slug"] == "default"


