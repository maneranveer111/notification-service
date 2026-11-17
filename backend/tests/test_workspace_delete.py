"""
Tests for workspace deletion:
- POST /workspaces/current/delete
- Permission enforcement (owner only, not admin/viewer/API key/master key)
- Name and password confirmation
- Default workspace protection
- Complete cascaded deletion of all associated entities
- NULLing out of delivery_events.notification_id
- Quota and rate-limit handling
- Foreign-key schema guard
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.database import Base, SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.api_client import ApiClient
from app.models.delivery_attempt import DeliveryAttempt
from app.models.delivery_event import DeliveryEvent
from app.models.invitation import Invitation
from app.models.notification import Notification
from app.models.provider_credential import ProviderCredential
from app.models.suppression import Suppression
from app.models.template import Template
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password
from app.services.workspace_delete import check_delete_rate_limit, cleanup_quota_keys, delete_workspace
from app.tasks.notification_tasks import _deliver, dispatch_scheduled

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


def _create_workspace(db, name="Test WS", slug=None, owner=None):
    if not slug:
        slug = f"ws-{uuid.uuid4().hex[:8]}"
    ws = Workspace(
        name=name,
        slug=slug,
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


def _token_for(user, ws, role="owner"):
    return create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        workspace_id=ws.id if ws else None,
    )


# ---------------------------------------------------------------------------
# 1. Successful deletion cascades all associated entities
# ---------------------------------------------------------------------------

def test_owner_deletes_workspace_cascades_all_entities(db):
    owner = _create_user(db, password="correct-password")
    member = _create_user(db)
    ws1 = _create_workspace(db, name="Acme Ops", slug=f"acme-{uuid.uuid4().hex[:6]}", owner=owner)
    ws2 = _create_workspace(db, name="Backup Team", slug=f"backup-{uuid.uuid4().hex[:6]}", owner=owner)

    # Member joins ws1
    db.add(Membership(user_id=member.id, workspace_id=ws1.id, role="viewer"))
    member.last_workspace_id = ws1.id
    db.commit()

    # Create ApiClient
    raw_key = secrets.token_hex(24)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_client = ApiClient(
        workspace_id=ws1.id,
        name="Backend API",
        key_hash=key_hash,
        key_prefix="ak_live",
    )
    db.add(api_client)
    db.flush()

    # Create Template
    template = Template(
        workspace_id=ws1.id,
        client_id=api_client.id,
        name="Welcome Email",
        channel="email",
        body_template="Hello {{ name }}",
    )
    db.add(template)
    db.flush()

    # Create Notification
    notif = Notification(
        workspace_id=ws1.id,
        client_id=api_client.id,
        template_id=template.id,
        channel="email",
        recipient="recipient@example.com",
        subject="Welcome",
        body="Hello world",
        status="delivered",
    )
    db.add(notif)
    db.flush()

    # Create DeliveryAttempt
    attempt = DeliveryAttempt(
        notification_id=notif.id,
        attempt_number=1,
        provider="smtp",
        started_at=datetime.now(timezone.utc),
        duration_ms=120,
        outcome="success",
    )
    db.add(attempt)

    # Create DeliveryEvent
    event = DeliveryEvent(
        notification_id=notif.id,
        provider="smtp",
        event_type="delivered",
    )
    db.add(event)

    # Create Suppression
    suppression = Suppression(
        workspace_id=ws1.id,
        channel="email",
        recipient="suppressed@example.com",
    )
    db.add(suppression)

    # Create ProviderCredential
    cred = ProviderCredential(
        workspace_id=ws1.id,
        provider="smtp",
        config_encrypted="dummy_encrypted_data",
    )
    db.add(cred)

    # Create Invitation
    inv = Invitation(
        workspace_id=ws1.id,
        email="invited@example.com",
        role="viewer",
        invited_by=owner.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(inv)
    db.commit()

    event_id = event.id
    ws1_id = ws1.id
    ws2_id = ws2.id
    notif_id = notif.id

    token = _token_for(owner, ws1, "owner")
    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "Acme Ops", "password": "correct-password"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["deleted"] is True
    assert data["login"] is not None
    assert data["login"]["workspace"]["id"] == str(ws2_id)

    # Clear identity map cache so fresh state is fetched from DB
    db.rollback()

    # Verify entities deleted
    assert db.get(Workspace, ws1_id) is None
    assert db.get(Workspace, ws2_id) is not None
    assert db.scalar(select(func.count(Notification.id)).where(Notification.workspace_id == ws1_id)) == 0
    assert db.scalar(select(func.count(DeliveryAttempt.id)).where(DeliveryAttempt.notification_id == notif_id)) == 0
    assert db.scalar(select(func.count(Template.id)).where(Template.workspace_id == ws1_id)) == 0
    assert db.scalar(select(func.count(ApiClient.id)).where(ApiClient.workspace_id == ws1_id)) == 0
    assert db.scalar(select(func.count(Suppression.id)).where(Suppression.workspace_id == ws1_id)) == 0
    assert db.scalar(select(func.count(ProviderCredential.id)).where(ProviderCredential.workspace_id == ws1_id)) == 0
    assert db.scalar(select(func.count(Invitation.id)).where(Invitation.workspace_id == ws1_id)) == 0
    assert db.scalar(select(func.count(Membership.user_id)).where(Membership.workspace_id == ws1_id)) == 0

    # DeliveryEvent was deleted
    assert db.get(DeliveryEvent, event_id) is None

    # Users last_workspace_id reset
    db.refresh(member)
    assert member.last_workspace_id is None


# ---------------------------------------------------------------------------
# 2. Validation failures: wrong name (422) and wrong password (400)
# ---------------------------------------------------------------------------

def test_delete_wrong_name_returns_422(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="My Workspace", owner=owner)
    token = _token_for(owner, ws)

    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "Wrong Name", "password": "password123!"},
    )
    assert resp.status_code == 422
    assert db.get(Workspace, ws.id) is not None


def test_delete_wrong_password_returns_400(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="My Workspace", owner=owner)
    token = _token_for(owner, ws)

    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "My Workspace", "password": "wrong-password"},
    )
    assert resp.status_code == 400
    assert db.get(Workspace, ws.id) is not None


# ---------------------------------------------------------------------------
# 3. Role enforcement: admin (403), viewer (403), api key (403), master key (403)
# ---------------------------------------------------------------------------

def test_admin_cannot_delete_workspace(db):
    owner = _create_user(db)
    admin = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="Admin WS", owner=owner)
    db.add(Membership(user_id=admin.id, workspace_id=ws.id, role="admin"))
    db.commit()

    token = _token_for(admin, ws, "admin")
    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "Admin WS", "password": "password123!"},
    )
    assert resp.status_code == 403
    assert db.get(Workspace, ws.id) is not None


def test_viewer_cannot_delete_workspace(db):
    owner = _create_user(db)
    viewer = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="Viewer WS", owner=owner)
    db.add(Membership(user_id=viewer.id, workspace_id=ws.id, role="viewer"))
    db.commit()

    token = _token_for(viewer, ws, "viewer")
    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "Viewer WS", "password": "password123!"},
    )
    assert resp.status_code == 403
    assert db.get(Workspace, ws.id) is not None


def test_api_key_cannot_delete_workspace(db):
    owner = _create_user(db)
    ws = _create_workspace(db, name="API WS", owner=owner)
    raw_key = secrets.token_hex(24)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    client_row = ApiClient(
        workspace_id=ws.id,
        name="Key Client",
        key_hash=key_hash,
        key_prefix="ak_test",
    )
    db.add(client_row)
    db.commit()

    resp = client.post(
        "/workspaces/current/delete",
        headers={"X-API-Key": raw_key},
        json={"confirm_name": "API WS", "password": "password123!"},
    )
    assert resp.status_code == 403
    assert db.get(Workspace, ws.id) is not None


def test_master_key_cannot_delete_workspace(db):
    owner = _create_user(db)
    ws = _create_workspace(db, name="Master Key WS", owner=owner)

    resp = client.post(
        "/workspaces/current/delete",
        headers={"X-API-Key": settings.api_key},
        json={"confirm_name": "Master Key WS", "password": "password123!"},
    )
    assert resp.status_code == 403
    assert db.get(Workspace, ws.id) is not None


# ---------------------------------------------------------------------------
# 4. Default workspace protection (409)
# ---------------------------------------------------------------------------

def test_default_workspace_protected_from_deletion(db):
    owner = _create_user(db, password="password123!")
    # Check if default workspace already exists or create one
    def_ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
    if not def_ws:
        def_ws = Workspace(name="Default Workspace", slug="default")
        db.add(def_ws)
        db.commit()
        db.refresh(def_ws)

    # Add owner membership
    m = db.get(Membership, (owner.id, def_ws.id))
    if not m:
        db.add(Membership(user_id=owner.id, workspace_id=def_ws.id, role="owner"))
        db.commit()

    token = _token_for(owner, def_ws, "owner")
    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": def_ws.name, "password": "password123!"},
    )
    assert resp.status_code == 409
    assert db.get(Workspace, def_ws.id) is not None


# ---------------------------------------------------------------------------
# 5. Deleted workspace API key returns 401
# ---------------------------------------------------------------------------

def test_deleted_workspace_api_key_returns_401(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="API Test WS", owner=owner)
    raw_key = secrets.token_hex(24)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    client_row = ApiClient(
        workspace_id=ws.id,
        name="API Test Client",
        key_hash=key_hash,
        key_prefix="ak_test",
    )
    db.add(client_row)
    db.commit()

    token = _token_for(owner, ws)
    del_resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "API Test WS", "password": "password123!"},
    )
    assert del_resp.status_code == 200

    # Test API key on tenant endpoint
    resp = client.get("/notifications", headers={"X-API-Key": raw_key})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 6. Webhook token invalid after workspace delete
# ---------------------------------------------------------------------------

def test_webhook_token_invalid_after_delete(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="WH Test WS", owner=owner)
    token_url = ws.webhook_token

    token = _token_for(owner, ws)
    client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "WH Test WS", "password": "password123!"},
    )

    resp = client.post(f"/webhooks/events/{token_url}", json={"test": "data"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Other member token behavior after deletion
# ---------------------------------------------------------------------------

def test_other_member_token_behavior_after_delete(db):
    owner = _create_user(db, password="password123!")
    member = _create_user(db)
    ws1 = _create_workspace(db, name="Shared WS", owner=owner)
    ws2 = _create_workspace(db, name="Member Own WS", owner=member)

    db.add(Membership(user_id=member.id, workspace_id=ws1.id, role="viewer"))
    db.commit()

    member_ws1_token = _token_for(member, ws1, "viewer")

    # Owner deletes ws1
    owner_token = _token_for(owner, ws1)
    client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"confirm_name": "Shared WS", "password": "password123!"},
    )

    # Member hits tenant route with old ws1 token -> 403 Forbidden
    resp = client.get("/workspaces/current", headers={"Authorization": f"Bearer {member_ws1_token}"})
    assert resp.status_code == 403

    # Member hits /auth/me -> 200, only lists remaining workspaces
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {member_ws1_token}"})
    assert me_resp.status_code == 200
    workspaces = me_resp.json().get("workspaces", [])
    ws_ids = [w["id"] for w in workspaces]
    assert str(ws1.id) not in ws_ids
    assert str(ws2.id) in ws_ids


# ---------------------------------------------------------------------------
# 8. Single workspace owner: login is None in response
# ---------------------------------------------------------------------------

def test_single_workspace_owner_login_is_null(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="Only WS", owner=owner)

    token = _token_for(owner, ws)
    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "Only WS", "password": "password123!"},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert resp.json()["login"] is None


# ---------------------------------------------------------------------------
# 9. Scheduled notifications deleted, dispatch_scheduled ok
# ---------------------------------------------------------------------------

def test_scheduled_notifications_deleted_dispatch_scheduled_ok(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="Sched WS", owner=owner)
    notif = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="sched@example.com",
        subject="Scheduled",
        body="Text",
        status="pending",
        scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db.add(notif)
    db.commit()

    token = _token_for(owner, ws)
    client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "Sched WS", "password": "password123!"},
    )

    # dispatch_scheduled should run cleanly
    with patch("app.tasks.notification_tasks.enqueue_notification"):
        res = dispatch_scheduled()
    assert isinstance(res, dict)
    assert "dispatched_count" in res


# ---------------------------------------------------------------------------
# 10. Worker _deliver handles deleted notification id gracefully
# ---------------------------------------------------------------------------

def test_worker_deliver_deleted_notification():
    mock_task = MagicMock()
    missing_id = str(uuid.uuid4())
    res = _deliver(mock_task, missing_id, MagicMock())
    assert res == {"status": "error", "reason": "not found"}


# ---------------------------------------------------------------------------
# 11. Transaction rollback on error
# ---------------------------------------------------------------------------

def test_rollback_on_deletion_error(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="Rollback WS", owner=owner)

    with patch("app.services.workspace_delete.delete_workspace", side_effect=RuntimeError("Simulated DB error")):
        token = _token_for(owner, ws)
        resp = client.post(
            "/workspaces/current/delete",
            headers={"Authorization": f"Bearer {token}"},
            json={"confirm_name": "Rollback WS", "password": "password123!"},
        )
        assert resp.status_code == 500

    # Workspace still exists
    assert db.get(Workspace, ws.id) is not None


# ---------------------------------------------------------------------------
# 12. Redis cleanup failure is resilient
# ---------------------------------------------------------------------------

def test_redis_cleanup_failure_resilient(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="Redis Resilient WS", owner=owner)

    with patch("app.services.workspace_delete.cleanup_quota_keys", side_effect=Exception("Redis down")):
        token = _token_for(owner, ws)
        resp = client.post(
            "/workspaces/current/delete",
            headers={"Authorization": f"Bearer {token}"},
            json={"confirm_name": "Redis Resilient WS", "password": "password123!"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


# ---------------------------------------------------------------------------
# 13. Rate limit enforcement (5 per hour)
# ---------------------------------------------------------------------------

def test_delete_rate_limit_exceeded_429(db):
    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="RL WS", owner=owner)
    token = _token_for(owner, ws)

    with patch("app.services.workspace_delete.check_delete_rate_limit", return_value=False):
        resp = client.post(
            "/workspaces/current/delete",
            headers={"Authorization": f"Bearer {token}"},
            json={"confirm_name": "RL WS", "password": "password123!"},
        )
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 14. Schema guard: all tables with FK to workspaces.id are handled
# ---------------------------------------------------------------------------

def test_schema_guard_all_foreign_keys_handled():
    """
    Ensure every SQLAlchemy table referencing workspaces.id is explicitly
    accounted for in the delete_workspace function.
    """
    import inspect
    from app.services import workspace_delete

    src = inspect.getsource(workspace_delete.delete_workspace)

    tables_referencing_workspaces = []
    for table_name, table in Base.metadata.tables.items():
        for fk in table.foreign_keys:
            target = fk.target_fullname
            if target == "workspaces.id":
                tables_referencing_workspaces.append(table_name)

    # Expected referencing tables in current schema
    for tbl in tables_referencing_workspaces:
        # Each model table name or corresponding Model name must appear in the delete function source
        # or have ondelete CASCADE
        assert any(
            t in src.lower() for t in [tbl.lower(), tbl.rstrip("s").lower()]
        ), f"Table {tbl} references workspaces.id but is not handled in delete_workspace!"


# ---------------------------------------------------------------------------
# 15. Delivery events preservation: unmatched events and other workspaces
# ---------------------------------------------------------------------------

def test_delete_workspace_preserves_unmatched_delivery_events(db):
    unmatched_event = DeliveryEvent(
        notification_id=None,
        provider="webhook",
        event_type="unmatched_bounce",
    )
    db.add(unmatched_event)
    db.commit()
    unmatched_id = unmatched_event.id

    owner = _create_user(db, password="password123!")
    ws = _create_workspace(db, name="WS Unmatched Test", owner=owner)
    notif = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="test@example.com",
        subject="Test",
        status="delivered",
    )
    db.add(notif)
    db.commit()

    ws_event = DeliveryEvent(
        notification_id=notif.id,
        provider="smtp",
        event_type="delivered",
    )
    db.add(ws_event)
    db.commit()
    ws_event_id = ws_event.id

    token = _token_for(owner, ws)
    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm_name": "WS Unmatched Test", "password": "password123!"},
    )
    assert resp.status_code == 200

    db.rollback()
    # Workspace event is deleted
    assert db.get(DeliveryEvent, ws_event_id) is None
    # Unmatched event remains intact
    unmatched = db.get(DeliveryEvent, unmatched_id)
    assert unmatched is not None
    assert unmatched.notification_id is None


def test_delete_workspace_preserves_other_workspace_delivery_events(db):
    owner = _create_user(db, password="password123!")
    ws1 = _create_workspace(db, name="WS 1", owner=owner)
    ws2 = _create_workspace(db, name="WS 2", owner=owner)

    notif1 = Notification(
        workspace_id=ws1.id,
        channel="email",
        recipient="user1@example.com",
        subject="N1",
        status="delivered",
    )
    notif2 = Notification(
        workspace_id=ws2.id,
        channel="email",
        recipient="user2@example.com",
        subject="N2",
        status="delivered",
    )
    db.add_all([notif1, notif2])
    db.commit()

    ev1 = DeliveryEvent(notification_id=notif1.id, provider="smtp", event_type="delivered")
    ev2 = DeliveryEvent(notification_id=notif2.id, provider="smtp", event_type="delivered")
    db.add_all([ev1, ev2])
    db.commit()
    ev1_id = ev1.id
    ev2_id = ev2.id
    notif2_id = notif2.id

    token1 = _token_for(owner, ws1)
    resp = client.post(
        "/workspaces/current/delete",
        headers={"Authorization": f"Bearer {token1}"},
        json={"confirm_name": "WS 1", "password": "password123!"},
    )
    assert resp.status_code == 200

    db.rollback()
    # WS1 delivery event is deleted
    assert db.get(DeliveryEvent, ev1_id) is None
    # WS2 delivery event is preserved with its notification_id intact
    ev2_db = db.get(DeliveryEvent, ev2_id)
    assert ev2_db is not None
    assert ev2_db.notification_id == notif2_id

