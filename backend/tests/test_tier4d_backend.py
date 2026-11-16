"""
Tier 4D backend tests: Public config endpoint, credential decryption error message,
and email service log hygiene.
"""
import contextlib
import secrets
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password
from app.tasks.notification_tasks import send_email_task, send_sms_task, send_webhook_task

client = TestClient(app)
settings = get_settings()

SECRET_KEYS = [
    "secret_key",
    "encryption_key",
    "jwt_secret",
    "database_url",
    "smtp_password",
    "brevo_api_key",
    "rate_limit_storage_uri",
    "twilio_auth_token",
]


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


def _make_user(db, email=None, role="admin", is_superadmin=False, password="password123!"):
    email = email or f"u_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_workspace(db, name="Test WS"):
    slug = f"ws-{uuid.uuid4().hex[:8]}"
    ws = Workspace(
        name=name,
        slug=slug,
        webhook_token=secrets.token_urlsafe(32),
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


def _add_member(db, user, ws, role="owner"):
    mem = Membership(user_id=user.id, workspace_id=ws.id, role=role)
    db.add(mem)
    db.commit()
    return mem


def _auth_headers(user, ws_id):
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=ws_id,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test 1: GET /public/config returns 200 with expected fields
# ---------------------------------------------------------------------------

def test_public_config_open():
    resp = client.get("/public/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "app_name" in data
    assert "signup_mode" in data
    assert "require_email_verification" in data
    assert "turnstile_site_key" in data
    assert "needs_setup" in data


# ---------------------------------------------------------------------------
# Test 2: needs_setup is True when no users exist and signup_mode != "closed"
# ---------------------------------------------------------------------------

def test_needs_setup_true_when_empty():
    from app.database import get_db
    from app.main import app

    mock_db = MagicMock()
    mock_db.scalar.return_value = 0
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        with _settings_override(signup_mode="open"):
            resp = client.get("/public/config")
        assert resp.status_code == 200
        assert resp.json()["needs_setup"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test 3: Response never contains secret keys
# ---------------------------------------------------------------------------

def test_config_no_secrets():
    resp = client.get("/public/config")
    assert resp.status_code == 200
    data = resp.json()
    for key in SECRET_KEYS:
        assert key not in data, f"Secret key '{key}' should not appear in /public/config response"


# ---------------------------------------------------------------------------
# Test 4: Provider test with decrypt failure returns "Credential decryption failed"
# ---------------------------------------------------------------------------

def test_provider_test_decrypt_error(db):
    from cryptography.fernet import Fernet
    fernet_key = Fernet.generate_key().decode()

    with _settings_override(encryption_key=fernet_key):
        user = _make_user(db, is_superadmin=True)
        ws = _create_workspace(db)
        _add_member(db, user, ws, "owner")
        h = _auth_headers(user, ws.id)

        # First create a provider credential so the endpoint finds it
        resp_put = client.put(
            "/providers/brevo",
            headers=h,
            json={"api_key": "xkeysib-testkey", "from_email": "test@example.com"},
        )
        assert resp_put.status_code == 200

    # Now patch decrypt_json to raise an exception to simulate decrypt failure
    with patch("app.api.providers.decrypt_json", side_effect=Exception("some internal error")):
        with _settings_override(encryption_key=fernet_key):
            resp = client.post(
                "/providers/brevo/test",
                headers=h,
                json={"to": "dest@example.com"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error"] == "Credential decryption failed"
    assert "some internal error" not in data.get("error", "")


# ---------------------------------------------------------------------------
# Test 5: Email service never logs response body content
# ---------------------------------------------------------------------------

def test_email_service_no_body_logged(caplog):
    import logging
    from app.services.email_service import send_email
    from app.services.providers import BrevoConfig

    fake_secret = "FAKE_SECRET_KEY_abc123"

    # Build a mock requests.Response whose text contains the fake secret
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = f"Unauthorized: invalid key {fake_secret}"
    mock_response.json.return_value = {"message": f"invalid key {fake_secret}"}

    # requests.RequestException subclass that has a response attribute
    exc = requests.exceptions.HTTPError(f"401 Client Error: {fake_secret}")
    exc.response = mock_response

    brevo_cfg = BrevoConfig(api_key="testkey", from_email="from@example.com")

    with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
        with patch("app.services.email_service.requests.post", side_effect=exc):
            try:
                send_email(
                    recipient="dest@example.com",
                    subject="Test",
                    body="Body",
                    providers=[("brevo", brevo_cfg)],
                )
            except Exception:
                pass

    # Verify the fake secret never appears in any log record
    for record in caplog.records:
        assert fake_secret not in record.getMessage(), (
            f"Log record contains secret text: {record.getMessage()}"
        )
