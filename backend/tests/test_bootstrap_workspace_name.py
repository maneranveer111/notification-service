"""
Tests for Spec 4:
First-run setup workspace name:
1. First-user bootstrap with workspace_name renames default workspace (keeps slug='default', plan='unlimited').
2. First-user bootstrap without workspace_name keeps 'Default Workspace'.
3. Normal (non-bootstrap) signup creates a new workspace.
"""
import uuid
import pytest
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
    try:
        clean_users_and_non_default_workspaces(db)

        resp = client.post(
            "/auth/signup",
            json={
                "email": "bootstrap_admin1@example.com",
                "password": "Password123!",
                "workspace_name": "My Custom Org",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["workspace"]["name"] == "My Custom Org"
        assert data["workspace"]["slug"] == "default"

        default_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
        assert default_ws.name == "My Custom Org"
    finally:
        clean_users_and_non_default_workspaces(db)
        db.close()


def test_bootstrap_omitted_workspace_name_keeps_default():
    db = SessionLocal()
    try:
        clean_users_and_non_default_workspaces(db)

        resp = client.post(
            "/auth/signup",
            json={
                "email": "bootstrap_admin2@example.com",
                "password": "Password123!",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["workspace"]["name"] == "Default Workspace"
        assert data["workspace"]["slug"] == "default"

        default_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
        assert default_ws.name == "Default Workspace"
    finally:
        clean_users_and_non_default_workspaces(db)
        db.close()


def test_normal_signup_creates_new_workspace():
    db = SessionLocal()
    try:
        clean_users_and_non_default_workspaces(db)

        # 1. Bootstrap user
        resp1 = client.post(
            "/auth/signup",
            json={
                "email": "bootstrap_admin3@example.com",
                "password": "Password123!",
            },
        )
        assert resp1.status_code == 201

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
