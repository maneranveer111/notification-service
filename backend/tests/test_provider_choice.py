import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.limiter import limiter
from app.main import app
from app.models.notification import Notification
from app.models.provider_credential import ProviderCredential
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.crypto import encrypt_json
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password
from app.services.providers import resolve_email_providers

client = TestClient(app)
settings = get_settings()


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


def _create_user(db, email=None, password="password123!", role="user", is_superadmin=False):
    if not email:
        email = f"user_{uuid.uuid4().hex[:8]}@example.com"
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


def _create_workspace(db, name="Test WS", slug=None, owner=None, use_platform=False, preferred=None):
    if not slug:
        slug = f"ws-{uuid.uuid4().hex[:8]}"
    ws = Workspace(
        name=name,
        slug=slug,
        use_platform_providers=use_platform,
        preferred_email_provider=preferred,
        webhook_token=secrets.token_urlsafe(32),
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)

    if owner:
        m = Membership(user_id=owner.id, workspace_id=ws.id, role="owner")
        db.add(m)
        owner.last_workspace_id = ws.id
        db.commit()

    return ws


def _token_for(user, ws):
    return create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=ws.id if ws else None,
    )


def _add_credential(db, ws_id, provider, config_dict):
    now = datetime.now(timezone.utc)
    cred = ProviderCredential(
        workspace_id=ws_id,
        provider=provider,
        config_encrypted=encrypt_json(config_dict),
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(cred)
    db.commit()
    return cred


# ---------------------------------------------------------------------------
# 1. Selection logic: per-send requested_provider is strict (no fallback)
# ---------------------------------------------------------------------------
def test_persend_provider_strict_no_fallback(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner)
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    _add_credential(db, ws.id, "smtp", {
        "host": "smtp.example.com", "port": 587, "username": "u", "password": "p", "from_email": "s@example.com"
    })

    # When brevo is requested, only brevo must be returned
    resolved = resolve_email_providers(db, ws, requested_provider="brevo")
    assert len(resolved) == 1
    assert resolved[0][0] == "brevo"

    # When smtp is requested, only smtp must be returned
    resolved_smtp = resolve_email_providers(db, ws, requested_provider="smtp")
    assert len(resolved_smtp) == 1
    assert resolved_smtp[0][0] == "smtp"


# ---------------------------------------------------------------------------
# 2. Workspace preference goes first and still falls back
# ---------------------------------------------------------------------------
def test_workspace_preference_first_with_fallback(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner, preferred="smtp")
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    _add_credential(db, ws.id, "smtp", {
        "host": "smtp.example.com", "port": 587, "username": "u", "password": "p", "from_email": "s@example.com"
    })

    resolved = resolve_email_providers(db, ws)
    assert len(resolved) == 2
    assert resolved[0][0] == "smtp"  # preferred is first
    assert resolved[1][0] == "brevo"  # fallback remains second


# ---------------------------------------------------------------------------
# 3. Automatic order unchanged when no preference and no per-send choice
# ---------------------------------------------------------------------------
def test_automatic_order_unchanged(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner, preferred=None)
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    _add_credential(db, ws.id, "smtp", {
        "host": "smtp.example.com", "port": 587, "username": "u", "password": "p", "from_email": "s@example.com"
    })

    resolved = resolve_email_providers(db, ws)
    assert len(resolved) == 2
    # Settings default is brevo,smtp
    assert resolved[0][0] == "brevo"
    assert resolved[1][0] == "smtp"


# ---------------------------------------------------------------------------
# 4. Single email: configured provider vs unconfigured 422
# ---------------------------------------------------------------------------
def test_single_email_provider_validation_and_storage(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner)
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    token = _token_for(owner, ws)

    # Request unconfigured smtp -> 422 provider_not_configured
    resp = client.post(
        "/notifications/email",
        headers={"Authorization": f"Bearer {token}"},
        json={"recipient": "user@example.com", "subject": "Hi", "body": "Hello", "provider": "smtp"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "provider_not_configured"

    # Request configured brevo -> 200 and stored
    resp = client.post(
        "/notifications/email",
        headers={"Authorization": f"Bearer {token}"},
        json={"recipient": "user@example.com", "subject": "Hi", "body": "Hello", "provider": "brevo"},
    )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]

    notif = db.get(Notification, uuid.UUID(notif_id))
    assert notif.requested_provider == "brevo"
    assert notif.provider == "brevo"


# ---------------------------------------------------------------------------
# 5. Scheduled email with provider validation and storage
# ---------------------------------------------------------------------------
def test_scheduled_email_provider_validation_and_storage(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner)
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    token = _token_for(owner, ws)

    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    resp = client.post(
        "/notifications/email",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "recipient": "user@example.com",
            "subject": "Hi",
            "body": "Hello",
            "scheduled_at": future_time,
            "provider": "brevo",
        },
    )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]

    notif = db.get(Notification, uuid.UUID(notif_id))
    assert notif.status == "scheduled"
    assert notif.requested_provider == "brevo"
    assert notif.provider == "brevo"


# ---------------------------------------------------------------------------
# 6. Bulk email: provider validation and storage
# ---------------------------------------------------------------------------
def test_bulk_email_provider_choice(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner)
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    token = _token_for(owner, ws)

    # Unconfigured provider -> 422
    resp = client.post(
        "/notifications/bulk",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "channel": "email",
            "recipients": [{"recipient": "r1@example.com"}, {"recipient": "r2@example.com"}],
            "subject": "Bulk",
            "body": "Bulk body",
            "provider": "smtp",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "provider_not_configured"

    # Configured provider -> success
    resp = client.post(
        "/notifications/bulk",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "channel": "email",
            "recipients": [{"recipient": "r1@example.com"}, {"recipient": "r2@example.com"}],
            "subject": "Bulk",
            "body": "Bulk body",
            "provider": "brevo",
        },
    )
    assert resp.status_code == 200
    batch_id = resp.json()["batch_id"]

    notifications = db.query(Notification).filter(Notification.batch_id == uuid.UUID(batch_id)).all()
    assert len(notifications) == 2
    for n in notifications:
        assert n.requested_provider == "brevo"
        assert n.provider == "brevo"


# ---------------------------------------------------------------------------
# 7. Preference endpoints: GET and PUT set/clear
# ---------------------------------------------------------------------------
def test_preference_endpoints_get_and_put(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner)
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    _add_credential(db, ws.id, "smtp", {
        "host": "smtp.example.com", "port": 587, "username": "u", "password": "p", "from_email": "s@example.com"
    })
    token = _token_for(owner, ws)

    # GET initial preference
    resp = client.get("/providers/email/preference", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] is None
    assert set(data["available"]) == {"brevo", "smtp"}

    # PUT set to smtp
    resp = client.put(
        "/providers/email/preference",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "smtp"},
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] == "smtp"

    db.refresh(ws)
    assert ws.preferred_email_provider == "smtp"

    # PUT clear preference (null)
    resp = client.put(
        "/providers/email/preference",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": None},
    )
    assert resp.status_code == 200
    assert resp.json()["provider"] is None

    db.refresh(ws)
    assert ws.preferred_email_provider is None


# ---------------------------------------------------------------------------
# 8. Preference endpoint: unconfigured provider -> 422
# ---------------------------------------------------------------------------
def test_preference_endpoint_unconfigured_422(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner)
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    token = _token_for(owner, ws)

    resp = client.put(
        "/providers/email/preference",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "smtp"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "provider_not_configured"


# ---------------------------------------------------------------------------
# 9. Preference endpoints: Viewer gets 403
# ---------------------------------------------------------------------------
def test_preference_endpoints_viewer_forbidden(db):
    owner = _create_user(db)
    viewer = _create_user(db)
    ws = _create_workspace(db, owner=owner)
    db.add(Membership(user_id=viewer.id, workspace_id=ws.id, role="viewer"))
    db.commit()

    viewer_token = _token_for(viewer, ws)

    resp_get = client.get("/providers/email/preference", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp_get.status_code == 403

    resp_put = client.put(
        "/providers/email/preference",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"provider": "brevo"},
    )
    assert resp_put.status_code == 403


# ---------------------------------------------------------------------------
# 10. Preference endpoints: Workspace isolation
# ---------------------------------------------------------------------------
def test_preference_endpoint_workspace_isolation(db):
    owner = _create_user(db)
    ws1 = _create_workspace(db, owner=owner)
    ws2 = _create_workspace(db, owner=owner)
    _add_credential(db, ws1.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    _add_credential(db, ws2.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})

    token1 = _token_for(owner, ws1)
    token2 = _token_for(owner, ws2)

    client.put("/providers/email/preference", headers={"Authorization": f"Bearer {token1}"}, json={"provider": "brevo"})

    resp2 = client.get("/providers/email/preference", headers={"Authorization": f"Bearer {token2}"})
    assert resp2.json()["provider"] is None


# ---------------------------------------------------------------------------
# 11. Provider filter on GET /notifications combined with status & channel & X-Total-Count
# ---------------------------------------------------------------------------
def test_notifications_provider_filter(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner)
    token = _token_for(owner, ws)

    # Insert notifications with different providers
    n1 = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="a@example.com",
        provider="brevo",
        status="sent",
    )
    n2 = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="b@example.com",
        provider="smtp",
        status="sent",
    )
    n3 = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="c@example.com",
        provider="brevo",
        status="pending",
    )
    db.add_all([n1, n2, n3])
    db.commit()

    # Filter by provider=brevo
    resp = client.get("/notifications?provider=brevo", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "2"
    assert len(resp.json()) == 2
    for item in resp.json():
        assert item["provider"] == "brevo"

    # Filter by provider=brevo AND status=sent
    resp = client.get("/notifications?provider=brevo&status=sent", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "1"
    assert resp.json()[0]["recipient"] == "a@example.com"


# ---------------------------------------------------------------------------
# 12. Workspace preference stored in notifications.provider when only preference exists
# ---------------------------------------------------------------------------
def test_creation_stores_preferred_provider_when_only_preference_exists(db):
    owner = _create_user(db)
    ws = _create_workspace(db, owner=owner, preferred="smtp")
    _add_credential(db, ws.id, "brevo", {"api_key": "k", "from_email": "b@example.com"})
    _add_credential(db, ws.id, "smtp", {
        "host": "smtp.example.com", "port": 587, "username": "u", "password": "p", "from_email": "s@example.com"
    })
    token = _token_for(owner, ws)

    # Send without specifying per-send provider
    resp = client.post(
        "/notifications/email",
        headers={"Authorization": f"Bearer {token}"},
        json={"recipient": "user@example.com", "subject": "Hi", "body": "Hello"},
    )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]

    notif = db.get(Notification, uuid.UUID(notif_id))
    assert notif.requested_provider is None
    assert notif.provider == "smtp"  # preference stored at creation
