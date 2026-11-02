"""
Tier 4A: Multi-tenancy tests.
Tests workspace isolation, role enforcement, and membership management.
"""
from datetime import datetime, timezone
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

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
MASTER_HEADERS = {"X-API-Key": settings.api_key}


@pytest.fixture(autouse=True)
def reset_limiter():
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


def _make_user_with_workspace(db, email, ws_role="owner", ws_id=None):
    """Create a user with membership in the specified (or default) workspace."""
    from app.services.tenancy import get_default_workspace_id
    user = User(
        email=email.lower(),
        password_hash=hash_password("password123"),
        role="admin" if ws_role in ("owner", "admin") else "viewer",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.flush()
    target_ws_id = ws_id or get_default_workspace_id(db)
    mem = Membership(user_id=user.id, workspace_id=target_ws_id, role=ws_role)
    db.add(mem)
    db.commit()
    db.refresh(user)
    return user


def _jwt_headers(user_id, email, role, workspace_id=None):
    token = create_access_token(user_id=user_id, email=email, role=role, workspace_id=workspace_id)
    return {"Authorization": f"Bearer {token}"}


def _create_workspace_via_api(user_headers, name):
    resp = client.post("/workspaces", headers=user_headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Schema Guard Tests
# ---------------------------------------------------------------------------

def test_workspace_id_not_null_on_notifications(db):
    result = db.execute(text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='notifications' AND column_name='workspace_id'"
    )).scalar()
    assert result == "NO", "workspace_id must be NOT NULL on notifications"


def test_workspace_id_not_null_on_templates(db):
    result = db.execute(text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='templates' AND column_name='workspace_id'"
    )).scalar()
    assert result == "NO"


def test_workspace_id_not_null_on_api_clients(db):
    result = db.execute(text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='api_clients' AND column_name='workspace_id'"
    )).scalar()
    assert result == "NO"


def test_workspace_id_not_null_on_suppressions(db):
    result = db.execute(text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='suppressions' AND column_name='workspace_id'"
    )).scalar()
    assert result == "NO"


# ---------------------------------------------------------------------------
# 2. Workspace CRUD Tests
# ---------------------------------------------------------------------------

def test_create_workspace(db):
    user_a = _make_user_with_workspace(db, f"ws_creator_{uuid.uuid4().hex[:8]}@example.com")
    headers = _jwt_headers(user_a.id, user_a.email, "owner")
    ws_data = _create_workspace_via_api(headers, f"Workspace {uuid.uuid4().hex[:6]}")
    assert "id" in ws_data
    assert ws_data["role"] == "owner"


def test_list_workspaces(db):
    user_a = _make_user_with_workspace(db, f"ws_list_{uuid.uuid4().hex[:8]}@example.com")
    headers = _jwt_headers(user_a.id, user_a.email, "owner")
    resp = client.get("/workspaces", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_switch_workspace(db):
    user_a = _make_user_with_workspace(db, f"switch_{uuid.uuid4().hex[:8]}@example.com")
    headers = _jwt_headers(user_a.id, user_a.email, "owner")

    ws2 = _create_workspace_via_api(headers, f"Second WS {uuid.uuid4().hex[:4]}")
    ws2_id = ws2["id"]

    switch_resp = client.post("/auth/switch-workspace", headers=headers, json={"workspace_id": ws2_id})
    assert switch_resp.status_code == 200
    data = switch_resp.json()
    assert "access_token" in data
    assert data["workspace"]["id"] == ws2_id


def test_switch_workspace_forbidden_if_not_member(db):
    user_a = _make_user_with_workspace(db, f"switch_forbid_{uuid.uuid4().hex[:8]}@example.com")
    headers = _jwt_headers(user_a.id, user_a.email, "owner")

    fake_ws_id = str(uuid.uuid4())
    resp = client.post("/auth/switch-workspace", headers=headers, json={"workspace_id": fake_ws_id})
    assert resp.status_code == 403


def test_get_current_workspace(db):
    user_a = _make_user_with_workspace(db, f"cur_ws_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=mem_a.workspace_id)

    resp = client.get("/workspaces/current", headers=h_a)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(mem_a.workspace_id)


def test_update_current_workspace(db):
    user_a = _make_user_with_workspace(db, f"upd_ws_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=mem_a.workspace_id)

    new_name = f"Renamed WS {uuid.uuid4().hex[:4]}"
    resp = client.patch("/workspaces/current", headers=h_a, json={"name": new_name})
    assert resp.status_code == 200
    assert resp.json()["name"] == new_name


# ---------------------------------------------------------------------------
# 3. Cross-Workspace Isolation Tests
# ---------------------------------------------------------------------------

def test_workspace_notification_isolation(db):
    user_a = _make_user_with_workspace(db, f"notif_a_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    ws_b = _create_workspace_via_api(h_a, f"WS B {uuid.uuid4().hex[:4]}")
    ws_b_id = ws_b["id"]
    user_b = _make_user_with_workspace(db, f"notif_b_{uuid.uuid4().hex[:8]}@example.com", ws_id=uuid.UUID(ws_b_id))
    h_b = _jwt_headers(user_b.id, user_b.email, "owner", workspace_id=uuid.UUID(ws_b_id))

    resp = client.post(
        "/notifications/email",
        headers=h_a,
        json={"recipient": "test@example.com", "subject": "WS A notification", "body": "Body A"},
    )
    assert resp.status_code == 200
    notif_a_id = resp.json()["id"]

    resp_b = client.get(f"/notifications/{notif_a_id}", headers=h_b)
    assert resp_b.status_code == 404


def test_workspace_notification_list_isolation(db):
    user_a = _make_user_with_workspace(db, f"list_a_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    ws_b = _create_workspace_via_api(h_a, f"WS B List {uuid.uuid4().hex[:4]}")
    ws_b_id = ws_b["id"]
    user_b = _make_user_with_workspace(db, f"list_b_{uuid.uuid4().hex[:8]}@example.com", ws_id=uuid.UUID(ws_b_id))
    h_b = _jwt_headers(user_b.id, user_b.email, "owner", workspace_id=uuid.UUID(ws_b_id))

    unique_email = f"isolation_target_{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/notifications/email",
        headers=h_a,
        json={"recipient": unique_email, "subject": "Private", "body": "Body"},
    )

    resp_b = client.get(f"/notifications?recipient={unique_email}", headers=h_b)
    assert resp_b.status_code == 200
    assert len(resp_b.json()) == 0


def test_workspace_template_isolation(db):
    user_a = _make_user_with_workspace(db, f"tmpl_a_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    ws_b = _create_workspace_via_api(h_a, f"WS B Tmpl {uuid.uuid4().hex[:4]}")
    ws_b_id = ws_b["id"]
    user_b = _make_user_with_workspace(db, f"tmpl_b_{uuid.uuid4().hex[:8]}@example.com", ws_id=uuid.UUID(ws_b_id))
    h_b = _jwt_headers(user_b.id, user_b.email, "owner", workspace_id=uuid.UUID(ws_b_id))

    resp = client.post(
        "/templates",
        headers=h_a,
        json={"name": f"tmpl_{uuid.uuid4().hex[:6]}", "channel": "email", "body_template": "Hello {{name}}"},
    )
    assert resp.status_code == 201
    tmpl_id = resp.json()["id"]

    resp_b = client.get(f"/templates/{tmpl_id}", headers=h_b)
    assert resp_b.status_code == 404


def test_cross_workspace_template_id_rejected(db):
    user_a = _make_user_with_workspace(db, f"cwtmpl_a_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    ws_b = _create_workspace_via_api(h_a, f"WS B CW {uuid.uuid4().hex[:4]}")
    ws_b_id = ws_b["id"]
    user_b = _make_user_with_workspace(db, f"cwtmpl_b_{uuid.uuid4().hex[:8]}@example.com", ws_id=uuid.UUID(ws_b_id))
    h_b = _jwt_headers(user_b.id, user_b.email, "owner", workspace_id=uuid.UUID(ws_b_id))

    resp = client.post(
        "/templates",
        headers=h_a,
        json={"name": f"tmpl_{uuid.uuid4().hex[:6]}", "channel": "email", "body_template": "Hello"},
    )
    assert resp.status_code == 201
    tmpl_a_id = resp.json()["id"]

    resp_b = client.post(
        "/notifications/email",
        headers=h_b,
        json={"recipient": "x@example.com", "template_id": tmpl_a_id},
    )
    assert resp_b.status_code == 422


def test_same_idempotency_key_different_workspaces_creates_two(db):
    user_a = _make_user_with_workspace(db, f"idem_a_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    ws_b = _create_workspace_via_api(h_a, f"WS Idem B {uuid.uuid4().hex[:4]}")
    ws_b_id = ws_b["id"]
    user_b = _make_user_with_workspace(db, f"idem_b_{uuid.uuid4().hex[:8]}@example.com", ws_id=uuid.UUID(ws_b_id))
    h_b = _jwt_headers(user_b.id, user_b.email, "owner", workspace_id=uuid.UUID(ws_b_id))

    shared_key = f"shared-{uuid.uuid4().hex[:6]}"

    resp_a = client.post(
        "/notifications/email",
        headers={**h_a, "Idempotency-Key": shared_key},
        json={"recipient": "u@example.com", "subject": "Subj", "body": "Body"},
    )
    assert resp_a.status_code == 200

    resp_b = client.post(
        "/notifications/email",
        headers={**h_b, "Idempotency-Key": shared_key},
        json={"recipient": "u@example.com", "subject": "Subj", "body": "Body"},
    )
    assert resp_b.status_code == 200
    assert resp_a.json()["id"] != resp_b.json()["id"]


def test_suppression_isolation_between_workspaces(db):
    user_a = _make_user_with_workspace(db, f"sup_a_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    ws_b = _create_workspace_via_api(h_a, f"WS B Sup {uuid.uuid4().hex[:4]}")
    ws_b_id = ws_b["id"]
    user_b = _make_user_with_workspace(db, f"sup_b_{uuid.uuid4().hex[:8]}@example.com", ws_id=uuid.UUID(ws_b_id))
    h_b = _jwt_headers(user_b.id, user_b.email, "owner", workspace_id=uuid.UUID(ws_b_id))

    target_email = f"sup_test_{uuid.uuid4().hex[:6]}@example.com"

    resp_sup = client.post(
        "/suppressions",
        headers=h_a,
        json={"channel": "email", "recipient": target_email, "reason": "bounce"},
    )
    assert resp_sup.status_code in (200, 201)

    resp_send_a = client.post(
        "/notifications/email",
        headers=h_a,
        json={"recipient": target_email, "subject": "A", "body": "B"},
    )
    assert resp_send_a.status_code == 200
    assert resp_send_a.json()["status"] == "suppressed"

    resp_send_b = client.post(
        "/notifications/email",
        headers=h_b,
        json={"recipient": target_email, "subject": "A", "body": "B"},
    )
    assert resp_send_b.status_code == 200
    assert resp_send_b.json()["status"] == "pending"


# ---------------------------------------------------------------------------
# 4. Role Restrictions (Viewer / Admin / Owner)
# ---------------------------------------------------------------------------

def test_viewer_cannot_send_notification(db):
    user_a = _make_user_with_workspace(db, f"vw_owner_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id

    user_v = _make_user_with_workspace(db, f"vw_viewer_{uuid.uuid4().hex[:8]}@example.com", ws_role="viewer", ws_id=ws_a_id)
    h_v = _jwt_headers(user_v.id, user_v.email, "viewer", workspace_id=ws_a_id)

    resp = client.post(
        "/notifications/email",
        headers=h_v,
        json={"recipient": "x@example.com", "subject": "S", "body": "B"},
    )
    assert resp.status_code == 403


def test_viewer_can_read_notifications(db):
    user_a = _make_user_with_workspace(db, f"vread_owner_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    resp = client.post(
        "/notifications/email",
        headers=h_a,
        json={"recipient": "x@example.com", "subject": "S", "body": "B"},
    )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]

    user_v = _make_user_with_workspace(db, f"vread_viewer_{uuid.uuid4().hex[:8]}@example.com", ws_role="viewer", ws_id=ws_a_id)
    h_v = _jwt_headers(user_v.id, user_v.email, "viewer", workspace_id=ws_a_id)

    resp_v = client.get(f"/notifications/{notif_id}", headers=h_v)
    assert resp_v.status_code == 200


def test_viewer_cannot_create_template(db):
    user_a = _make_user_with_workspace(db, f"vtmpl_owner_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    user_v = _make_user_with_workspace(db, f"vtmpl_viewer_{uuid.uuid4().hex[:8]}@example.com", ws_role="viewer", ws_id=ws_a_id)
    h_v = _jwt_headers(user_v.id, user_v.email, "viewer", workspace_id=ws_a_id)

    resp = client.post(
        "/templates",
        headers=h_v,
        json={"name": "T", "channel": "email", "body_template": "B"},
    )
    assert resp.status_code == 403


def test_admin_can_create_template(db):
    user_a = _make_user_with_workspace(db, f"adm_tmpl_{uuid.uuid4().hex[:8]}@example.com", ws_role="admin")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    h_a = _jwt_headers(user_a.id, user_a.email, "admin", workspace_id=mem_a.workspace_id)

    resp = client.post(
        "/templates",
        headers=h_a,
        json={"name": f"AdmTmpl_{uuid.uuid4().hex[:6]}", "channel": "email", "body_template": "Hello"},
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 5. Member Management & Ownership Rules
# ---------------------------------------------------------------------------

def test_list_members(db):
    user_a = _make_user_with_workspace(db, f"list_mem_o_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    resp = client.get("/workspaces/current/members", headers=h_a)
    assert resp.status_code == 200
    members = resp.json()
    assert len(members) >= 1
    assert any(m["user_id"] == str(user_a.id) for m in members)


def test_owner_can_promote_member(db):
    user_a = _make_user_with_workspace(db, f"add_mem_owner_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    user_b = _make_user_with_workspace(db, f"user_b_{uuid.uuid4().hex[:8]}@example.com", ws_role="viewer", ws_id=ws_a_id)

    resp = client.patch(
        f"/workspaces/current/members/{user_b.id}",
        headers=h_a,
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_cannot_change_own_role(db):
    user_a = _make_user_with_workspace(db, f"self_role_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    resp = client.patch(
        f"/workspaces/current/members/{user_a.id}",
        headers=h_a,
        json={"role": "viewer"},
    )
    assert resp.status_code == 409


def test_cannot_remove_self(db):
    user_a = _make_user_with_workspace(db, f"self_rem_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    resp = client.delete(f"/workspaces/current/members/{user_a.id}", headers=h_a)
    assert resp.status_code == 409


def test_admin_cannot_modify_owner(db):
    user_owner = _make_user_with_workspace(db, f"own_prot_{uuid.uuid4().hex[:8]}@example.com", ws_role="owner")
    mem_o = db.execute(select(Membership).where(Membership.user_id == user_owner.id)).scalars().first()
    ws_id = mem_o.workspace_id

    user_admin = _make_user_with_workspace(db, f"adm_prot_{uuid.uuid4().hex[:8]}@example.com", ws_role="admin", ws_id=ws_id)
    h_adm = _jwt_headers(user_admin.id, user_admin.email, "admin", workspace_id=ws_id)

    resp = client.patch(
        f"/workspaces/current/members/{user_owner.id}",
        headers=h_adm,
        json={"role": "viewer"},
    )
    assert resp.status_code == 403


def test_admin_cannot_grant_owner_role(db):
    user_owner = _make_user_with_workspace(db, f"own_grant_{uuid.uuid4().hex[:8]}@example.com", ws_role="owner")
    mem_o = db.execute(select(Membership).where(Membership.user_id == user_owner.id)).scalars().first()
    ws_id = mem_o.workspace_id

    user_admin = _make_user_with_workspace(db, f"adm_grant_{uuid.uuid4().hex[:8]}@example.com", ws_role="admin", ws_id=ws_id)
    h_adm = _jwt_headers(user_admin.id, user_admin.email, "admin", workspace_id=ws_id)

    user_viewer = _make_user_with_workspace(db, f"vw_grant_{uuid.uuid4().hex[:8]}@example.com", ws_role="viewer", ws_id=ws_id)

    resp = client.patch(
        f"/workspaces/current/members/{user_viewer.id}",
        headers=h_adm,
        json={"role": "owner"},
    )
    assert resp.status_code == 403


def test_leave_workspace(db):
    user_a = _make_user_with_workspace(db, f"leave_owner_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id

    user_b = _make_user_with_workspace(db, f"leave_viewer_{uuid.uuid4().hex[:8]}@example.com", ws_role="viewer", ws_id=ws_a_id)
    h_b = _jwt_headers(user_b.id, user_b.email, "viewer", workspace_id=ws_a_id)

    resp = client.post("/workspaces/current/leave", headers=h_b)
    assert resp.status_code == 204


def test_last_owner_cannot_leave(db):
    user_a = _make_user_with_workspace(db, f"last_leave_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=mem_a.workspace_id)

    # Create a fresh workspace where user_a is the sole owner
    solo_ws = _create_workspace_via_api(h_a, f"Solo WS {uuid.uuid4().hex[:4]}")
    solo_ws_id = uuid.UUID(solo_ws["id"])
    h_solo = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=solo_ws_id)

    resp = client.post("/workspaces/current/leave", headers=h_solo)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# 6. Superadmin & Platform Routes
# ---------------------------------------------------------------------------

def test_non_superadmin_cannot_access_admin_users(db):
    user_a = _make_user_with_workspace(db, f"non_sa_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    resp = client.get("/admin/users", headers=h_a)
    assert resp.status_code == 403


def test_master_key_can_access_admin_users():
    resp = client.get("/admin/users", headers=MASTER_HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_master_key_queues_field_present():
    resp = client.get("/stats/overview", headers=MASTER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "queues" in data
    assert isinstance(data["queues"], dict)


def test_non_superadmin_queues_field_empty(db):
    user_a = _make_user_with_workspace(db, f"queues_ws_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    resp = client.get("/stats/overview", headers=h_a)
    assert resp.status_code == 200
    data = resp.json()
    assert data["queues"] == {}


# ---------------------------------------------------------------------------
# 7. Auth Endpoints & Limits
# ---------------------------------------------------------------------------

def test_login_returns_workspace(db):
    user_a = _make_user_with_workspace(db, f"login_ws_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    user_a.password_hash = hash_password("testpassword123")
    db.commit()

    resp = client.post("/auth/login", json={"email": user_a.email, "password": "testpassword123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["workspace"] is not None
    assert str(ws_a_id) == data["workspace"]["id"]


def test_me_returns_workspace(db):
    user_a = _make_user_with_workspace(db, f"me_ws_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    resp = client.get("/auth/me", headers=h_a)
    assert resp.status_code == 200
    data = resp.json()
    assert data["workspace"] is not None
    assert str(ws_a_id) == data["workspace"]["id"]
    assert isinstance(data["workspaces"], list)


def test_user_without_membership_gets_403_on_tenant_routes(db):
    user_no_ws = User(
        email=f"no_ws_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password"),
        role="viewer",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user_no_ws)
    db.commit()
    db.refresh(user_no_ws)

    h = _jwt_headers(user_no_ws.id, user_no_ws.email, "viewer")
    resp = client.get("/notifications", headers=h)
    assert resp.status_code == 403


def test_user_without_membership_can_access_me(db):
    user_no_ws = User(
        email=f"no_ws_me_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password"),
        role="viewer",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user_no_ws)
    db.commit()
    db.refresh(user_no_ws)

    h = _jwt_headers(user_no_ws.id, user_no_ws.email, "viewer")
    resp = client.get("/auth/me", headers=h)
    assert resp.status_code == 200


def test_max_workspaces_per_user_limit(db):
    user_a = _make_user_with_workspace(db, f"max_ws_{uuid.uuid4().hex[:8]}@example.com")
    mem_a = db.execute(select(Membership).where(Membership.user_id == user_a.id)).scalars().first()
    ws_a_id = mem_a.workspace_id
    h_a = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=ws_a_id)

    max_ws = settings.max_workspaces_per_user
    for i in range(max_ws - 1):
        resp = client.post("/workspaces", headers=h_a, json={"name": f"Extra WS {i}"})
        assert resp.status_code == 201, f"Should succeed at iteration {i}: {resp.text}"

    resp = client.post("/workspaces", headers=h_a, json={"name": "One Too Many"})
    assert resp.status_code == 409


def test_jwt_with_unauthorized_ws_claim_returns_403(db):
    user_a = _make_user_with_workspace(db, f"ws_claim_{uuid.uuid4().hex[:8]}@example.com")
    foreign_ws_id = uuid.uuid4()
    h_foreign = _jwt_headers(user_a.id, user_a.email, "owner", workspace_id=foreign_ws_id)
    resp = client.get("/notifications", headers=h_foreign)
    assert resp.status_code == 403
