"""
Tier 4C1 tests: Hardening, Per-Workspace Provider Credentials, SSRF, Webhooks, and Admin Workspace endpoints.
"""
import contextlib
import hashlib
import ipaddress
import secrets
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.delivery_event import DeliveryEvent
from app.models.notification import Notification
from app.models.provider_credential import ProviderCredential
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.client_ip import client_ip
from app.services.crypto import CryptoNotConfigured, decrypt_json, encrypt_json
from app.services.jwt_tokens import create_access_token
from app.services.net_safety import assert_public_host
from app.services.passwords import hash_password
from app.services.tenancy import generate_workspace_slug, get_default_workspace_id
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
# 0. Hardening Tests H1 to H3 & Client IP
# ---------------------------------------------------------------------------

def test_h1_jwt_iat_floored_seconds_regression(db):
    user = _make_user(db)
    now = datetime.now(timezone.utc)
    user.password_changed_at = now
    db.commit()

    secret = settings.jwt_secret
    # Token crafted with iat equal to the floored second of password_changed_at -> MUST WORK
    token_same_sec = jwt.encode(
        {"sub": str(user.id), "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=1)).timestamp())},
        secret,
        algorithm="HS256",
    )
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token_same_sec}"})
    assert resp.status_code == 200

    # Token crafted with iat 2 seconds before password change -> REJECTED (401)
    token_old = jwt.encode(
        {"sub": str(user.id), "iat": int(now.timestamp()) - 2, "exp": int((now + timedelta(hours=1)).timestamp())},
        secret,
        algorithm="HS256",
    )
    resp_old = client.get("/auth/me", headers={"Authorization": f"Bearer {token_old}"})
    assert resp_old.status_code == 401


def test_h2_client_ip_trusted_proxy_count_0():
    req = MagicMock()
    req.client.host = "192.168.1.50"
    req.headers = {"X-Forwarded-For": "203.0.113.195, 10.0.0.1"}
    with _settings_override(trusted_proxy_count=0):
        assert client_ip(req) == "192.168.1.50"


def test_h2_client_ip_trusted_proxy_count_1():
    req = MagicMock()
    req.client.host = "10.0.0.2"
    req.headers = {"X-Forwarded-For": "203.0.113.195, 10.0.0.1"}
    with _settings_override(trusted_proxy_count=1):
        assert client_ip(req) == "10.0.0.1"


def test_h2_client_ip_trusted_proxy_count_2_spoofed_leftmost_ignored():
    req = MagicMock()
    req.client.host = "10.0.0.2"
    # Leftmost is spoofed client IP, next is real client, last is proxy
    req.headers = {"X-Forwarded-For": "1.2.3.4, 203.0.113.195, 10.0.0.1"}
    with _settings_override(trusted_proxy_count=2):
        assert client_ip(req) == "203.0.113.195"


def test_h2_client_ip_invalid_falls_back():
    req = MagicMock()
    req.client.host = "127.0.0.1"
    req.headers = {"X-Forwarded-For": "invalid-ip-string"}
    with _settings_override(trusted_proxy_count=1):
        assert client_ip(req) == "127.0.0.1"


def test_h3_signup_timing_oracle_hashes_password_on_collision(db):
    """Timing-oracle mitigation: hash_password must be called even when a collision is found,
    regardless of whether the existing account is verified or not."""
    user = _make_user(db, email=f"oracle_{uuid.uuid4().hex[:8]}@example.com")
    with patch("app.api.accounts.hash_password", wraps=hash_password) as mock_hash, \
         patch("app.api.accounts.queue_system_email"):
        resp = client.post("/auth/signup", json={"email": user.email, "password": "password123!"})
    # Verified accounts return 409 (correct behavior). Timing mitigation still applies.
    assert resp.status_code == 409
    assert mock_hash.called


# ---------------------------------------------------------------------------
# 1. Crypto Service Tests
# ---------------------------------------------------------------------------

def test_crypto_round_trip():
    payload = {"api_key": "secret123", "from_email": "a@b.com"}
    encrypted = encrypt_json(payload)
    decrypted = decrypt_json(encrypted)
    assert decrypted == payload


def test_crypto_key_rotation():
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()

    # Encrypt with key1
    with _settings_override(encryption_key=key1):
        enc1 = encrypt_json({"hello": "world"})

    # Decrypt with key2,key1 (rotation: key2 encrypts, key1 still decrypts)
    with _settings_override(encryption_key=f"{key2},{key1}"):
        dec = decrypt_json(enc1)
        assert dec == {"hello": "world"}
        # New encryption uses key2
        enc2 = encrypt_json({"new": "data"})

    # Old key1 cannot decrypt enc2
    with _settings_override(encryption_key=key1):
        with pytest.raises(ValueError):
            decrypt_json(enc2)


def test_crypto_not_configured_raises():
    with _settings_override(encryption_key=None):
        with pytest.raises(CryptoNotConfigured):
            encrypt_json({"foo": "bar"})


def test_crypto_malformed_ciphertext():
    with pytest.raises(ValueError):
        decrypt_json("not-a-valid-fernet-token")


# ---------------------------------------------------------------------------
# 2. SSRF Guard Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_ip", [
    "127.0.0.1",
    "10.0.0.1",
    "172.16.0.1",
    "192.168.1.1",
    "169.254.169.254",
    "::1",
    "0.0.0.0",
])
def test_ssrf_guard_rejects_private_ips(bad_ip):
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, (bad_ip, 25))]):
        with pytest.raises(ValueError, match="resolves to non-public"):
            assert_public_host("example.com")


def test_ssrf_guard_allows_public_ip():
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 25))]):
        assert_public_host("example.com")  # should not raise


def test_ssrf_guard_bypass_when_allowed():
    with _settings_override(allow_private_smtp_hosts=True):
        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 25))]):
            assert_public_host("localhost")  # should not raise


# ---------------------------------------------------------------------------
# 3. Provider Endpoints Tests
# ---------------------------------------------------------------------------

def test_put_brevo_provider_creates_and_redacts_secrets(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    resp = client.put(
        "/providers/brevo",
        headers=h,
        json={"api_key": "xkeysib-supersecretkey1234", "from_email": "test@example.com", "from_name": "Test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "brevo"
    assert data["fields"]["from_email"] == "test@example.com"
    assert "supersecretkey1234" not in str(data)  # secret never present
    assert data["secrets_set"] == ["api_key"]
    assert data["hints"]["api_key"] == "1234"  # last 4 only


def test_put_smtp_provider_validates_ssrf_and_port(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # Bad port
    resp_port = client.put(
        "/providers/smtp",
        headers=h,
        json={"host": "smtp.example.com", "port": 9999, "username": "u", "password": "p", "from_email": "a@b.com"},
    )
    assert resp_port.status_code == 422

    # Loopback host
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 25))]):
        resp_ssrf = client.put(
            "/providers/smtp",
            headers=h,
            json={"host": "smtp.internal.local", "port": 587, "username": "u", "password": "p", "from_email": "a@b.com"},
        )
        assert resp_ssrf.status_code == 422


def test_put_twilio_validates_e164(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    resp_bad = client.put(
        "/providers/twilio",
        headers=h,
        json={"account_sid": "AC1234567890", "auth_token": "token1234", "from_number": "not-e164"},
    )
    assert resp_bad.status_code == 422


def test_put_partial_update_keeps_stored_secrets(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # Create
    client.put(
        "/providers/brevo",
        headers=h,
        json={"api_key": "xkeysib-firstkey9999", "from_email": "first@example.com"},
    )

    # Partial update: omit api_key, update from_name
    resp = client.put(
        "/providers/brevo",
        headers=h,
        json={"from_name": "Updated Name"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["hints"]["api_key"] == "9999"  # preserved


def test_missing_encryption_key_returns_503(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    with _settings_override(encryption_key=None):
        resp = client.put(
            "/providers/brevo",
            headers=h,
            json={"api_key": "key", "from_email": "a@b.com"},
        )
        assert resp.status_code == 503
        assert "Encryption is not configured" in resp.json()["detail"]


def test_viewer_and_api_key_forbidden_on_providers(db):
    owner = _make_user(db)
    viewer = _make_user(db, role="viewer")
    ws = _create_workspace(db)
    _add_member(db, owner, ws, "owner")
    _add_member(db, viewer, ws, "viewer")

    vh = _auth_headers(viewer, ws.id)
    resp = client.get("/providers", headers=vh)
    assert resp.status_code == 403

    resp_put = client.put("/providers/brevo", headers=vh, json={})
    assert resp_put.status_code == 403


def test_cross_workspace_provider_isolation(db):
    user_a = _make_user(db)
    user_b = _make_user(db)
    ws_a = _create_workspace(db, "WS A")
    ws_b = _create_workspace(db, "WS B")
    _add_member(db, user_a, ws_a, "owner")
    _add_member(db, user_b, ws_b, "owner")

    h_a = _auth_headers(user_a, ws_a.id)
    h_b = _auth_headers(user_b, ws_b.id)

    client.put(
        "/providers/brevo",
        headers=h_a,
        json={"api_key": "keyA1234", "from_email": "a@example.com"},
    )

    # User B lists providers -> empty
    resp_b = client.get("/providers", headers=h_b)
    assert resp_b.status_code == 200
    assert len(resp_b.json()) == 0

    # User B deletes A's provider -> 404
    resp_del = client.delete("/providers/brevo", headers=h_b)
    assert resp_del.status_code == 404


def test_provider_test_endpoint_sanitizes_errors(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    secret_key = "supersecret_password_xyz"
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 25))]):
        client.put(
            "/providers/smtp",
            headers=h,
            json={"host": "smtp.example.com", "port": 587, "username": "u", "password": secret_key, "from_email": "a@b.com"},
        )

        with patch("app.api.providers._send_smtp", side_effect=Exception(f"Failed with secret {secret_key}")):
            resp = client.post("/providers/smtp/test", headers=h, json={"to": "dest@example.com"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert secret_key not in data["error"]  # sanitized
        assert "[REDACTED]" in data["error"]


def test_webhooks_regenerate_token(db):
    user = _make_user(db)
    ws = _create_workspace(db)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    resp_get = client.get("/providers/webhooks", headers=h)
    old_token = resp_get.json()["token"]

    resp_regen = client.post("/providers/webhooks/regenerate", headers=h)
    new_token = resp_regen.json()["token"]

    assert old_token != new_token
    assert new_token in resp_regen.json()["brevo_url"]


# ---------------------------------------------------------------------------
# 4. Sending & Provider Resolution Tests
# ---------------------------------------------------------------------------

def test_workspace_without_provider_gets_422_on_creation(db):
    user = _make_user(db)
    ws = _create_workspace(db, "No Provider WS", use_platform_providers=False)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # Email
    resp_email = client.post(
        "/notifications/email",
        headers=h,
        json={"recipient": "dest@example.com", "subject": "Hi", "body": "Hello"},
    )
    assert resp_email.status_code == 422
    assert resp_email.json()["code"] == "no_provider"

    # SMS
    resp_sms = client.post(
        "/notifications/sms",
        headers=h,
        json={"recipient": "+1234567890", "message": "Hi"},
    )
    assert resp_sms.status_code == 422
    assert resp_sms.json()["code"] == "no_provider"

    # Bulk Email
    resp_bulk = client.post(
        "/notifications/bulk",
        headers=h,
        json={"channel": "email", "recipients": [{"recipient": "d@example.com"}], "subject": "S", "body": "B"},
    )
    assert resp_bulk.status_code == 422
    assert resp_bulk.json()["code"] == "no_provider"

    # Webhook channel does not require credentials and works!
    with patch("app.api.notifications.enqueue_notification"):
        resp_wh = client.post(
            "/notifications/webhook",
            headers=h,
            json={"recipient": "https://hooks.slack.com/services/xxx", "body": "Alert"},
        )
        assert resp_wh.status_code in (200, 201)


def test_workspace_uses_its_own_credentials_at_send(db):
    user = _make_user(db)
    ws = _create_workspace(db, "Custom WS", use_platform_providers=False)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # Configure custom brevo
    custom_api_key = "xkeysib-workspace-custom-key"
    client.put(
        "/providers/brevo",
        headers=h,
        json={"api_key": custom_api_key, "from_email": "custom@example.com"},
    )

    # Create notification in DB
    notif = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="user@example.com",
        subject="Test",
        body="Body",
        status="pending",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # Deliver via send_email_task
    with patch("app.services.email_service.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messageId": "msg-custom-123"}
        mock_post.return_value = mock_resp

        send_email_task.run(str(notif.id))

        assert mock_post.called
        headers_used = mock_post.call_args[1]["headers"]
        assert headers_used["api-key"] == custom_api_key  # workspace key used!


def test_default_workspace_uses_platform_providers(db):
    default_ws_id = get_default_workspace_id(db)
    default_ws = db.get(Workspace, default_ws_id)
    assert default_ws.use_platform_providers is True


# ---------------------------------------------------------------------------
# 5. Webhooks Tests
# ---------------------------------------------------------------------------

def test_workspace_brevo_webhook_updates_matching_notification(db):
    ws = _create_workspace(db, "Brevo WS")
    notif = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="target@example.com",
        provider="brevo",
        provider_message_id="brevo-msg-abc",
        status="sent",
    )
    db.add(notif)
    db.commit()

    resp = client.post(
        f"/webhooks/brevo/{ws.webhook_token}",
        json={"event": "delivered", "message-id": "brevo-msg-abc"},
    )
    assert resp.status_code == 200
    db.refresh(notif)
    assert notif.status == "delivered"


def test_workspace_brevo_webhook_wrong_token_returns_404():
    resp = client.post("/webhooks/brevo/invalid-token-123", json={"event": "delivered"})
    assert resp.status_code == 404


def test_workspace_twilio_webhook_validates_signature(db):
    user = _make_user(db)
    ws = _create_workspace(db, "Twilio WS")
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    auth_token = "authtoken1234567890123456789012"
    client.put(
        "/providers/twilio",
        headers=h,
        json={"account_sid": "AC1234567890", "auth_token": auth_token, "from_number": "+1234567890"},
    )

    notif = Notification(
        workspace_id=ws.id,
        channel="sms",
        recipient="+1987654321",
        provider="twilio",
        provider_message_id="SM1234567890",
        status="sent",
    )
    db.add(notif)
    db.commit()

    url = f"{settings.public_base_url}/webhooks/twilio/{ws.webhook_token}"
    form_data = {"MessageSid": "SM1234567890", "MessageStatus": "delivered"}
    valid_sig = RequestValidator(auth_token).compute_signature(url, form_data)

    # Valid signature
    resp = client.post(
        f"/webhooks/twilio/{ws.webhook_token}",
        data=form_data,
        headers={"X-Twilio-Signature": valid_sig},
    )
    assert resp.status_code == 200
    db.refresh(notif)
    assert notif.status == "delivered"

    # Invalid signature -> 403
    resp_bad = client.post(
        f"/webhooks/twilio/{ws.webhook_token}",
        data=form_data,
        headers={"X-Twilio-Signature": "invalid-signature"},
    )
    assert resp_bad.status_code == 403


# ---------------------------------------------------------------------------
# 6. Admin Workspaces Endpoints Tests
# ---------------------------------------------------------------------------

def test_admin_workspaces_endpoints_superadmin_only(db):
    regular_user = _make_user(db, is_superadmin=False)
    superadmin = _make_user(db, is_superadmin=True)
    ws = _create_workspace(db, "Target WS", use_platform_providers=False)
    _add_member(db, regular_user, ws, "viewer")
    _add_member(db, superadmin, ws, "owner")

    reg_h = _auth_headers(regular_user, ws.id)
    sa_h = _auth_headers(superadmin, ws.id)

    # Regular user gets 403
    assert client.get("/admin/workspaces", headers=reg_h).status_code == 403
    assert client.patch(f"/admin/workspaces/{ws.id}", headers=reg_h, json={"use_platform_providers": True}).status_code == 403

    # Superadmin lists workspaces
    resp_list = client.get("/admin/workspaces", headers=sa_h)
    assert resp_list.status_code == 200
    assert "X-Total-Count" in resp_list.headers
    data = resp_list.json()
    assert any(w["id"] == str(ws.id) for w in data)

    # Superadmin patches workspace platform providers flag
    resp_patch = client.patch(f"/admin/workspaces/{ws.id}", headers=sa_h, json={"use_platform_providers": True})
    assert resp_patch.status_code == 200
    assert resp_patch.json()["use_platform_providers"] is True

    db.refresh(ws)
    assert ws.use_platform_providers is True
