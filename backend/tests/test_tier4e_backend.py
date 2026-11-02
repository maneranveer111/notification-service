"""
Tier 4E backend tests: Provider precedence logic and suppression reason validation.

Tests:
  1. Own email credentials win over use_platform_providers=True
  2. Fallback to platform when no own email credentials
  3. No credentials, no platform fallback -> empty list
  4. Own SMS credentials win over use_platform_providers=True
  5-8. Suppression reason validation (opt_out/bounce accepted; complaint/manual rejected)
"""
import contextlib
import secrets
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.provider_credential import ProviderCredential
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.crypto import encrypt_json
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password
from app.services.providers import resolve_email_providers, resolve_sms_provider
from app.services.tenancy import generate_workspace_slug
from app.tasks.notification_tasks import send_email_task, send_sms_task, send_webhook_task

client = TestClient(app)
settings = get_settings()


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


@pytest.fixture(autouse=True)
def ensure_encryption_key():
    key = Fernet.generate_key().decode()
    with _settings_override(encryption_key=key):
        yield key


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


def _create_workspace(db, name="Test WS", use_platform_providers=False):
    ws = Workspace(
        name=name,
        slug=generate_workspace_slug(name),
        use_platform_providers=use_platform_providers,
        webhook_token=secrets.token_urlsafe(32),
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


def _add_member(db, user, workspace, role="owner"):
    mem = Membership(user_id=user.id, workspace_id=workspace.id, role=role)
    db.add(mem)
    db.commit()
    return mem


def _auth_headers(user, workspace_id=None):
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=workspace_id,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Own email credentials win over use_platform_providers=True
# ---------------------------------------------------------------------------

def test_1_own_email_creds_win_over_platform(db):
    ws = _create_workspace(db, name="OwnEmailWS", use_platform_providers=True)

    own_from_email = "own-brevo@workspace.example.com"
    config_data = {
        "api_key": "xkeysib-own-workspace-key-9999",
        "from_email": own_from_email,
        "from_name": "Own Workspace",
    }
    cred = ProviderCredential(
        workspace_id=ws.id,
        provider="brevo",
        config_encrypted=encrypt_json(config_data),
        is_active=True,
    )
    db.add(cred)
    db.commit()

    # Override platform brevo settings to a clearly different from_email
    with _settings_override(
        brevo_api_key="platform-key-0000",
        brevo_from_email="platform@platform.example.com",
        email_provider_order="brevo,smtp",
    ):
        result = resolve_email_providers(db, ws)

    assert len(result) > 0
    provider_name, provider_config = result[0]
    assert provider_name == "brevo"
    # Must use the workspace's own from_email, not the platform one
    assert provider_config.from_email == own_from_email
    assert provider_config.from_email != "platform@platform.example.com"


# ---------------------------------------------------------------------------
# 2. Fallback to platform when no own email credentials exist
# ---------------------------------------------------------------------------

def test_2_fallback_to_platform_when_no_own_creds(db):
    ws = _create_workspace(db, name="FallbackEmailWS", use_platform_providers=True)
    # No ProviderCredential rows for this workspace

    platform_from_email = "platform@example.com"
    with _settings_override(
        brevo_api_key="test-key-platform",
        brevo_from_email=platform_from_email,
        email_provider_order="brevo,smtp",
    ):
        result = resolve_email_providers(db, ws)

    assert len(result) > 0
    provider_name, provider_config = result[0]
    assert provider_name == "brevo"
    assert provider_config.from_email == platform_from_email


# ---------------------------------------------------------------------------
# 3. No credentials, no platform fallback -> empty list
# ---------------------------------------------------------------------------

def test_3_no_creds_no_platform_fallback(db):
    ws = _create_workspace(db, name="NoCreditWS", use_platform_providers=False)
    # No ProviderCredential rows for this workspace

    # Even if platform keys exist, use_platform_providers=False and no own creds -> []
    with _settings_override(
        brevo_api_key="test-key-platform",
        brevo_from_email="platform@example.com",
        email_provider_order="brevo,smtp",
    ):
        result = resolve_email_providers(db, ws)

    assert result == []


# ---------------------------------------------------------------------------
# 4. Own SMS credentials win over use_platform_providers=True
# ---------------------------------------------------------------------------

def test_4_own_sms_creds_win_over_platform(db):
    ws = _create_workspace(db, name="OwnSMSWS", use_platform_providers=True)

    own_from_number = "+19995550001"
    config_data = {
        "account_sid": "ACworkspace1234567890123456789012",
        "auth_token": "workspace_auth_token_123456789012",
        "from_number": own_from_number,
    }
    cred = ProviderCredential(
        workspace_id=ws.id,
        provider="twilio",
        config_encrypted=encrypt_json(config_data),
        is_active=True,
    )
    db.add(cred)
    db.commit()

    # Override platform twilio settings to a clearly different from_number
    with _settings_override(
        twilio_account_sid="ACplatform1234567890123456789012",
        twilio_auth_token="platform_auth_token_123456789012",
        twilio_from_number="+10000000000",
    ):
        result = resolve_sms_provider(db, ws)

    assert result is not None
    # Must use the workspace's own from_number, not the platform one
    assert result.from_number == own_from_number
    assert result.from_number != "+10000000000"
    # Callback URL must include the workspace's webhook_token
    assert ws.webhook_token in result.status_callback


# ---------------------------------------------------------------------------
# 5. Suppression reason 'opt_out' is accepted
# ---------------------------------------------------------------------------

def test_5_suppression_reason_opt_out_accepted(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    resp = client.post(
        "/suppressions",
        headers=h,
        json={"channel": "email", "recipient": "optout@example.com", "reason": "opt_out"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 6. Suppression reason 'bounce' is accepted
# ---------------------------------------------------------------------------

def test_6_suppression_reason_bounce_accepted(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    resp = client.post(
        "/suppressions",
        headers=h,
        json={"channel": "email", "recipient": "bounce@example.com", "reason": "bounce"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 7. Suppression reason 'complaint' is rejected (422)
# ---------------------------------------------------------------------------

def test_7_suppression_reason_complaint_rejected(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    resp = client.post(
        "/suppressions",
        headers=h,
        json={"channel": "email", "recipient": "complaint@example.com", "reason": "complaint"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 8. Suppression reason 'manual' is rejected (422)
# ---------------------------------------------------------------------------

def test_8_suppression_reason_manual_rejected(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    resp = client.post(
        "/suppressions",
        headers=h,
        json={"channel": "email", "recipient": "manual@example.com", "reason": "manual"},
    )
    assert resp.status_code == 422
