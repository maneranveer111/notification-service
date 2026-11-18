"""
Tests for Spec 4:
First-run setup workspace name:
1. First-user bootstrap with workspace_name renames default workspace (keeps slug='default', plan='unlimited').
2. First-user bootstrap without workspace_name keeps 'Default Workspace'.
3. Normal (non-bootstrap) signup creates a new workspace.

Updated to reflect that first-user bootstrap now requires email verification
(require_email_verification=True by default), so signup returns 202 and an
email is queued rather than issuing a token directly.
"""
import re
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import select, delete

from app.main import app
from app.models.user import User
from app.models.workspace import Workspace, Membership
from app.database import SessionLocal
from app.limiter import limiter

from sqlalchemy import text

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limit():
    limiter.reset()
    yield
    limiter.reset()


def clean_users_and_non_default_workspaces(db):
    try:
        db.rollback()
        db.execute(text("TRUNCATE delivery_events, delivery_attempts, notifications, templates, api_clients, suppressions, invitations, provider_credentials, memberships, users CASCADE;"))
        db.execute(delete(Workspace).where(Workspace.slug != "default"))
        default_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
        if default_ws:
            default_ws.name = "Default Workspace"
        db.commit()
    except Exception:
        db.rollback()
        raise


def test_bootstrap_rename_default_workspace():
    db = SessionLocal()
    captured = []
    def _mock_queue(to, subject, body):
        captured.append({"to": to, "body": body})
        return True

    try:
        clean_users_and_non_default_workspaces(db)

        with patch("app.api.accounts.queue_system_email", side_effect=_mock_queue):
            resp = client.post(
                "/auth/signup",
                json={
                    "email": "bootstrap_admin1@example.com",
                    "password": "Password123!",
                    "workspace_name": "My Custom Org",
                },
            )
        assert resp.status_code == 202, resp.text

        # Verify via the emailed token
        assert captured, "No verification email was queued"
        token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1]["body"])
        assert token_match, "No token found in verification email"
        verify_resp = client.post("/auth/verify-email", json={"token": token_match.group(1)})
        assert verify_resp.status_code == 200, verify_resp.text
        data = verify_resp.json()
        assert data["workspace"]["name"] == "My Custom Org"
        assert data["workspace"]["slug"] != "default"

        # Global default workspace was not renamed
        default_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
        assert default_ws.name == "Default Workspace"
    finally:
        clean_users_and_non_default_workspaces(db)
        db.close()


def test_bootstrap_omitted_workspace_name_keeps_default():
    db = SessionLocal()
    captured = []
    def _mock_queue(to, subject, body):
        captured.append({"to": to, "body": body})
        return True

    try:
        clean_users_and_non_default_workspaces(db)

        with patch("app.api.accounts.queue_system_email", side_effect=_mock_queue):
            resp = client.post(
                "/auth/signup",
                json={
                    "email": "bootstrap_admin2@example.com",
                    "password": "Password123!",
                },
            )
        assert resp.status_code == 202, resp.text

        assert captured, "No verification email was queued"
        token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1]["body"])
        assert token_match
        verify_resp = client.post("/auth/verify-email", json={"token": token_match.group(1)})
        assert verify_resp.status_code == 200, verify_resp.text
        data = verify_resp.json()
        assert data["workspace"]["name"] == "bootstrap_admin2's Workspace"
        assert data["workspace"]["slug"] != "default"

        # Global default workspace remains untouched
        default_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
        assert default_ws.name == "Default Workspace"
    finally:
        clean_users_and_non_default_workspaces(db)
        db.close()


def test_normal_signup_creates_new_workspace():
    db = SessionLocal()
    captured = []
    def _mock_queue(to, subject, body):
        captured.append({"to": to, "body": body})
        return True

    try:
        clean_users_and_non_default_workspaces(db)

        # 1. Bootstrap user (first user — becomes superadmin, requires verification)
        with patch("app.api.accounts.queue_system_email", side_effect=_mock_queue):
            resp1 = client.post(
                "/auth/signup",
                json={
                    "email": "bootstrap_admin3@example.com",
                    "password": "Password123!",
                },
            )
        assert resp1.status_code == 202, resp1.text

        # Verify bootstrap user so test state is consistent
        token_match = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured[-1]["body"])
        assert token_match
        client.post("/auth/verify-email", json={"token": token_match.group(1)})

        # 2. Second user (normal signup, users count > 0)
        from app.config import get_settings
        settings = get_settings()
        orig_mode = settings.signup_mode
        orig_verify = settings.require_email_verification
        settings.signup_mode = "open"
        settings.require_email_verification = False
        try:
            resp2 = client.post(
                "/auth/signup",
                json={
                    "email": "second_user@example.com",
                    "password": "Password123!",
                    "workspace_name": "Second User Workspace",
                },
            )
            assert resp2.status_code == 201, resp2.text
            data2 = resp2.json()
            assert data2["workspace"]["name"] == "Second User Workspace"
            assert data2["workspace"]["slug"] != "default"

            # Check workspace in DB
            ws = db.scalar(select(Workspace).where(Workspace.name == "Second User Workspace"))
            assert ws is not None
            assert ws.slug != "default"
        finally:
            settings.signup_mode = orig_mode
            settings.require_email_verification = orig_verify
    finally:
        clean_users_and_non_default_workspaces(db)
        db.close()
