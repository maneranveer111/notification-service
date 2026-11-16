import contextlib
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.config import get_settings
from app.main import app
from app.models.user import User
from app.services.passwords import hash_password

client = TestClient(app)


@contextlib.contextmanager
def _settings_override(**kwargs):
    obj = get_settings()
    saved = {k: getattr(obj, k) for k in kwargs}
    try:
        for k, v in kwargs.items():
            object.__setattr__(obj, k, v)
        yield
    finally:
        for k, v in saved.items():
            object.__setattr__(obj, k, v)


def test_public_config_cache_control_header_present():
    """Verify GET /public/config returns Cache-Control: no-store header."""
    resp = client.get("/public/config")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"


def test_public_config_reflects_each_signup_mode():
    """Verify returned signup_mode reflects the active setting for each mode."""
    for mode in ["open", "invite_only", "closed"]:
        with _settings_override(signup_mode=mode):
            resp = client.get("/public/config")
            assert resp.status_code == 200
            data = resp.json()
            assert data["signup_mode"] == mode


def test_needs_setup_true_on_empty_users_and_false_otherwise(db):
    """Verify needs_setup is True on an empty users table and False when users exist."""
    # Ensure users table is empty for first check
    db.execute(delete(User))
    db.commit()

    with _settings_override(signup_mode="open"):
        resp = client.get("/public/config")
        assert resp.status_code == 200
        assert resp.json()["needs_setup"] is True

    # Closed signup mode with empty table must still be False
    with _settings_override(signup_mode="closed"):
        resp = client.get("/public/config")
        assert resp.status_code == 200
        assert resp.json()["needs_setup"] is False

    # Insert a user -> needs_setup must now be False
    user = User(
        email=f"setup_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Password123!"),
        role="admin",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()

    with _settings_override(signup_mode="open"):
        resp = client.get("/public/config")
        assert resp.status_code == 200
        assert resp.json()["needs_setup"] is False
