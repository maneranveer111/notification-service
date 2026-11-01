from datetime import datetime, timezone
import re
from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.main import app
from app.models.delivery_attempt import DeliveryAttempt
from app.models.notification import Notification
from app.models.suppression import Suppression
from app.models.template import Template
from app.models.user import User
from app.schemas.stats import TimelineItem
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password, verify_password
from app.tasks.notification_tasks import (
    _deliver,
    send_email_task,
    send_sms_task,
    send_webhook_task,
)

client = TestClient(app)
settings = get_settings()
MASTER_HEADERS = {"X-API-Key": settings.api_key}


@pytest.fixture(autouse=True)
def reset_limiter_and_tasks():
    limiter.reset()
    with patch.object(send_email_task, "apply_async", return_value=MagicMock()) as m_email, \
         patch.object(send_sms_task, "apply_async", return_value=MagicMock()) as m_sms, \
         patch.object(send_webhook_task, "apply_async", return_value=MagicMock()) as m_webhook:
        yield m_email, m_sms, m_webhook
    limiter.reset()


def _create_test_user(db, email: str, password: str = "securepassword123", role: str = "viewer", is_active: bool = True):
    from app.models.workspace import Membership
    from app.services.tenancy import get_default_workspace_id
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role=role,
        is_superadmin=(role == "admin"),
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    try:
        def_ws_id = get_default_workspace_id(db)
        ws_role = "owner" if role == "admin" else "viewer"
        mem = Membership(user_id=user.id, workspace_id=def_ws_id, role=ws_role)
        db.add(mem)
    except Exception:
        pass
    db.commit()
    db.refresh(user)
    return user


def _auth_headers_for(user: User):
    token = create_access_token(user_id=user.id, email=user.email, role=user.role)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Passwords & JWT Unit Tests
# ---------------------------------------------------------------------------

def test_password_hash_and_verify():
    pwd = "mySuperSecretPassword123"
    h = hash_password(pwd)
    assert h.startswith("scrypt$")
    assert verify_password(pwd, h) is True
    assert verify_password("wrongPassword", h) is False


def test_jwt_create_and_decode():
    u_id = uuid.uuid4()
    token = create_access_token(user_id=u_id, email="test@example.com", role="admin")
    from app.services.jwt_tokens import decode_access_token
    payload = decode_access_token(token)
    assert payload["sub"] == str(u_id)
    assert payload["email"] == "test@example.com"
    assert payload["role"] == "admin"


# ---------------------------------------------------------------------------
# 2. Auth Endpoints: Login & Me
# ---------------------------------------------------------------------------

def test_login_success_and_auth_me():
    db = next(get_db())
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    user = _create_test_user(db, email=email, password="password123", role="viewer")

    # Login
    resp = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == settings.jwt_expire_minutes * 60
    assert "user" in data
    assert data["user"]["id"] == str(user.id)
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "viewer"

    # Verify last_login_at updated
    db.refresh(user)
    assert user.last_login_at is not None

    # Auth Me
    token = data["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == email
    assert me_data["role"] == "viewer"
    assert me_data["can_write"] is False
    assert me_data["is_admin"] is False


def test_login_invalid_credentials_and_inactive():
    db = next(get_db())
    email = f"inactive_{uuid.uuid4().hex[:8]}@example.com"
    _create_test_user(db, email=email, password="password123", is_active=False)

    # Inactive user
    resp = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert resp.status_code == 401
    assert "deactivated" in resp.json()["detail"].lower()

    # Wrong password
    resp = client.post("/auth/login", json={"email": email, "password": "wrong"})
    assert resp.status_code == 401

    # Unknown email
    resp = client.post("/auth/login", json={"email": "nonexistent@example.com", "password": "password123"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. Viewer vs Admin Permissions (require_write, require_admin)
# ---------------------------------------------------------------------------

def test_viewer_cannot_mutate_notifications_or_templates():
    db = next(get_db())
    v_user = _create_test_user(db, email=f"viewer_{uuid.uuid4().hex[:8]}@example.com", role="viewer")
    v_headers = _auth_headers_for(v_user)

    # Viewer POST email -> 403
    resp = client.post(
        "/notifications/email",
        headers=v_headers,
        json={"recipient": "dest@example.com", "subject": "Hi", "body": "Hello"},
    )
    assert resp.status_code == 403

    # Viewer POST template -> 403
    resp = client.post(
        "/templates",
        headers=v_headers,
        json={"name": "T1", "channel": "email", "body_template": "Hello {{name}}"},
    )
    assert resp.status_code == 403

    # Viewer POST suppression -> 403
    resp = client.post(
        "/suppressions",
        headers=v_headers,
        json={"channel": "email", "recipient": "sup@example.com", "reason": "opt_out"},
    )
    assert resp.status_code == 403

    # Viewer CAN read notifications & templates
    assert client.get("/notifications", headers=v_headers).status_code == 200
    assert client.get("/templates", headers=v_headers).status_code == 200


def test_viewer_sees_all_notifications_and_templates():
    db = next(get_db())
    # Create an ApiClient first to satisfy FK constraint
    from app.models.api_client import ApiClient
    client_rec = ApiClient(
        name=f"TestClient_{uuid.uuid4().hex[:12]}",
        key_hash=uuid.uuid4().hex,
        key_prefix="nk_live_1234",
        is_active=True,
    )
    db.add(client_rec)
    db.commit()
    db.refresh(client_rec)
    c_id = client_rec.id

    n = Notification(
        channel="email",
        recipient="client_scoped@example.com",
        subject="Client Subj",
        body="Client Body",
        status="sent",
        client_id=c_id,
    )
    t = Template(
        name=f"tpl_{uuid.uuid4().hex[:6]}",
        channel="email",
        body_template="Template Body",
        client_id=c_id,
    )
    db.add(n)
    db.add(t)
    db.commit()

    v_user = _create_test_user(db, email=f"viewer_see_{uuid.uuid4().hex[:8]}@example.com", role="viewer")
    v_headers = _auth_headers_for(v_user)

    # Viewer should be able to get this notification and template
    n_resp = client.get(f"/notifications/{n.id}", headers=v_headers)
    assert n_resp.status_code == 200
    assert n_resp.json()["id"] == str(n.id)

    t_resp = client.get(f"/templates/{t.id}", headers=v_headers)
    assert t_resp.status_code == 200
    assert t_resp.json()["id"] == str(t.id)


# ---------------------------------------------------------------------------
# 4. Admin User Management CRUD & Guardrails
# ---------------------------------------------------------------------------

def test_admin_user_crud_and_guardrails():
    db = next(get_db())
    admin_user = _create_test_user(db, email=f"admin_{uuid.uuid4().hex[:8]}@example.com", role="admin")
    admin_headers = _auth_headers_for(admin_user)

    # 1. Create a second admin user
    email2 = f"admin2_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/admin/users",
        headers=admin_headers,
        json={"email": email2, "password": "anotherpassword123", "role": "admin"},
    )
    assert resp.status_code == 201
    u2_data = resp.json()
    u2_id = u2_data["id"]

    # Duplicate email -> 409
    resp_dup = client.post(
        "/admin/users",
        headers=admin_headers,
        json={"email": email2, "password": "anotherpassword123", "role": "viewer"},
    )
    assert resp_dup.status_code == 409

    # 2. List users
    resp_list = client.get("/admin/users", headers=admin_headers)
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 2

    # 3. Self-demote protection -> 409
    resp_self_demote = client.patch(
        f"/admin/users/{admin_user.id}",
        headers=admin_headers,
        json={"role": "viewer"},
    )
    assert resp_self_demote.status_code == 409
    assert "demote your own" in resp_self_demote.json()["detail"].lower()

    # 4. Self-deactivate protection -> 409
    resp_self_deact = client.patch(
        f"/admin/users/{admin_user.id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert resp_self_deact.status_code == 409
    assert "deactivate your own" in resp_self_deact.json()["detail"].lower()

    # 5. Demoting the other admin works because there are 2 active admins
    resp_demote_u2 = client.patch(
        f"/admin/users/{u2_id}",
        headers=admin_headers,
        json={"role": "viewer"},
    )
    assert resp_demote_u2.status_code == 200
    assert resp_demote_u2.json()["role"] == "viewer"

    # Ensure admin_user is the only active admin remaining in DB
    for a in db.scalars(select(User).where(User.role == "admin", User.is_active == True, User.id != admin_user.id)).all():
        a.is_active = False
    db.commit()

    # 6. Now there is only 1 active admin (admin_user). Attempting to demote or deactivate via another admin key or master key
    resp_last_admin = client.patch(
        f"/admin/users/{admin_user.id}",
        headers=MASTER_HEADERS,
        json={"role": "viewer"},
    )
    assert resp_last_admin.status_code == 409
    assert "last active admin" in resp_last_admin.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 5. Delivery Attempt History & Timeline
# ---------------------------------------------------------------------------

def test_delivery_attempt_recording_and_timeline():
    db = next(get_db())
    notif = Notification(
        channel="sms",
        recipient="+1234567890",
        body="Attempt test message",
        status="pending",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    # Deliver SMS via _deliver
    mock_task = MagicMock()
    mock_task.request.retries = 0

    res = _deliver(mock_task, str(notif.id), lambda n: ("twilio", "SM12345"))
    assert res["status"] == "sent"

    # Timeline endpoint
    t_resp = client.get(f"/notifications/{notif.id}/timeline", headers=MASTER_HEADERS)
    assert t_resp.status_code == 200
    attempts = t_resp.json()
    assert len(attempts) >= 1
    assert attempts[0]["provider"] == "twilio"
    assert attempts[0]["outcome"] == "success"
    assert attempts[0]["attempt_number"] == 1


# ---------------------------------------------------------------------------
# 6. List Filters & X-Total-Count Headers
# ---------------------------------------------------------------------------

def test_list_notifications_filters_and_total_count_header():
    db = next(get_db())
    unique_tag = uuid.uuid4().hex[:6]
    n1 = Notification(
        channel="email",
        recipient=f"filter_{unique_tag}@example.com",
        subject="Subj 1",
        body="Body 1",
        status="sent",
    )
    n2 = Notification(
        channel="email",
        recipient=f"other_{unique_tag}@example.com",
        subject="Subj 2",
        body="Body 2",
        status="failed",
    )
    db.add(n1)
    db.add(n2)
    db.commit()

    # Recipient filter
    resp = client.get(f"/notifications?recipient={unique_tag}", headers=MASTER_HEADERS)
    assert resp.status_code == 200
    assert "X-Total-Count" in resp.headers
    assert int(resp.headers["X-Total-Count"]) == 2
    assert len(resp.json()) == 2

    # Status + Recipient filter
    resp_filtered = client.get(f"/notifications?recipient={unique_tag}&status=sent", headers=MASTER_HEADERS)
    assert resp_filtered.status_code == 200
    assert int(resp_filtered.headers["X-Total-Count"]) == 1
    assert resp_filtered.json()[0]["recipient"] == f"filter_{unique_tag}@example.com"


def test_templates_and_suppressions_total_count_header():
    # Templates total count header
    t_resp = client.get("/templates", headers=MASTER_HEADERS)
    assert t_resp.status_code == 200
    assert "X-Total-Count" in t_resp.headers

    # Suppressions total count header
    s_resp = client.get("/suppressions", headers=MASTER_HEADERS)
    assert s_resp.status_code == 200
    assert "X-Total-Count" in s_resp.headers


# ---------------------------------------------------------------------------
# 7. Stats Overview & Timeseries
# ---------------------------------------------------------------------------

def test_stats_overview_and_timeseries():
    # Overview
    resp = client.get("/stats/overview?window_hours=24", headers=MASTER_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "window_hours" in data
    assert "total" in data
    assert "totals_by_status" in data
    assert "by_channel" in data
    assert "by_provider" in data
    assert "success_rate" in data
    assert "avg_attempts" in data
    assert "top_errors" in data
    assert "queues" in data

    # Timeseries
    ts_resp = client.get("/stats/timeseries?window_hours=6&bucket_hours=1", headers=MASTER_HEADERS)
    assert ts_resp.status_code == 200
    ts_data = ts_resp.json()
    assert isinstance(ts_data, list)
    assert len(ts_data) >= 6
    for item in ts_data:
        assert set(item.keys()) == {"bucket", "ok", "failed", "other"}


# ---------------------------------------------------------------------------
# 8. Metrics & Request ID Middleware
# ---------------------------------------------------------------------------

def test_request_id_middleware_and_metrics_endpoint():
    # Test Request ID header returned and propagated
    custom_id = f"req-{uuid.uuid4()}"
    resp = client.get("/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == custom_id

    # Test Metrics endpoint
    headers = {}
    if settings.metrics_token:
        headers["Authorization"] = f"Bearer {settings.metrics_token}"
    m_resp = client.get("/metrics", headers=headers)
    assert m_resp.status_code == 200
    assert "http_requests_total" in m_resp.text
    assert "http_request_duration_seconds" in m_resp.text


def test_viewer_jwt_cannot_call_any_non_get_route():
    db = next(get_db())
    v_user = _create_test_user(db, email=f"viewer_all_{uuid.uuid4().hex[:8]}@example.com", role="viewer")
    v_headers = _auth_headers_for(v_user)

    dummy_uuid = str(uuid.uuid4())
    public_prefixes = ("/auth/login", "/unsubscribe", "/webhooks", "/metrics")

    tested_routes = []
    for route in app.routes:
        if not hasattr(route, "methods"):
            continue
        for method in route.methods:
            if method in ("GET", "HEAD", "OPTIONS"):
                continue
            if any(route.path.startswith(prefix) for prefix in public_prefixes):
                continue
            if route.path in ("/workspaces", "/workspaces/current/leave", "/auth/switch-workspace"):
                continue
            path = re.sub(r"\{[^}]+\}", dummy_uuid, route.path)
            resp = client.request(method, path, headers=v_headers, json={})
            assert resp.status_code == 403, f"Expected 403 for {method} {path}, got {resp.status_code}: {resp.text}"
            tested_routes.append((method, path))

    assert len(tested_routes) > 0


# ---------------------------------------------------------------------------
# 9. Targeted Contract Tests for Login, Stats Overview, and Timeseries
# ---------------------------------------------------------------------------

def test_login_contract_and_security():
    db = next(get_db())
    email = f"user_contract_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "securepassword123!"
    user = _create_test_user(db, email=email, password=pwd, role="admin")

    resp = client.post("/auth/login", json={"email": email, "password": pwd})
    assert resp.status_code == 200
    data = resp.json()

    # Required fields
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == settings.jwt_expire_minutes * 60
    assert "user" in data

    # User sub-object contract
    user_info = data["user"]
    assert set(user_info.keys()) == {"id", "email", "role"}
    assert user_info["id"] == str(user.id)
    assert user_info["email"] == email
    assert user_info["role"] == "admin"

    # Security: No sensitive hash or password exposure
    assert "password" not in data
    assert "password_hash" not in data
    assert "password" not in user_info
    assert "password_hash" not in user_info
    assert "scrypt$" not in resp.text
    assert pwd not in resp.text


def test_stats_overview_contract_and_avg_attempts():
    db = next(get_db())

    # Create a distinct Workspace and ApiClient for isolated stats calculation
    from app.models.api_client import ApiClient
    from app.models.workspace import Workspace
    import hashlib
    iso_ws = Workspace(name=f"StatsWS_{uuid.uuid4().hex[:6]}", slug=f"statsws-{uuid.uuid4().hex[:6]}")
    db.add(iso_ws)
    db.commit()
    db.refresh(iso_ws)

    raw_key = "nk_live_" + uuid.uuid4().hex
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    client_rec = ApiClient(
        workspace_id=iso_ws.id,
        name=f"StatsClient_{uuid.uuid4().hex[:8]}",
        key_hash=key_hash,
        key_prefix=raw_key[:12],
        is_active=True,
    )
    db.add(client_rec)
    db.commit()
    db.refresh(client_rec)
    c_headers = {"X-API-Key": raw_key}

    # 1. Empty reporting window test for client with 0 notifications
    resp_empty = client.get("/stats/overview?window_hours=24", headers=c_headers)
    assert resp_empty.status_code == 200
    data_empty = resp_empty.json()

    expected_fields = {
        "window_hours",
        "total",
        "totals_by_status",
        "by_channel",
        "by_provider",
        "success_rate",
        "avg_attempts",
        "top_errors",
        "queues",
    }
    assert set(data_empty.keys()) == expected_fields
    assert "by_status" not in data_empty
    assert "queue_depths" not in data_empty
    assert data_empty["total"] == 0
    assert data_empty["avg_attempts"] == 0.0
    assert data_empty["success_rate"] == 0.0
    assert data_empty["totals_by_status"] == {}
    assert data_empty["by_channel"] == {}
    assert data_empty["by_provider"] == {}
    assert data_empty["queues"] == {}

    # 2. Add notifications with specific attempt_count values: 2 and 4 (avg = 3.0)
    n1 = Notification(
        workspace_id=iso_ws.id,
        channel="email",
        recipient="test1@example.com",
        status="sent",
        attempt_count=2,
        client_id=client_rec.id,
    )
    n2 = Notification(
        workspace_id=iso_ws.id,
        channel="email",
        recipient="test2@example.com",
        status="failed",
        attempt_count=4,
        client_id=client_rec.id,
        error_message="SMTP connection error",
    )
    db.add(n1)
    db.add(n2)
    db.commit()

    resp_populated = client.get("/stats/overview?window_hours=24", headers=c_headers)
    assert resp_populated.status_code == 200
    data_populated = resp_populated.json()

    assert set(data_populated.keys()) == expected_fields
    assert data_populated["total"] == 2
    assert data_populated["avg_attempts"] == 3.0
    assert data_populated["totals_by_status"] == {"sent": 1, "failed": 1}
    assert data_populated["success_rate"] == 50.0
    assert len(data_populated["top_errors"]) == 1
    assert data_populated["top_errors"][0]["error"] == "SMTP connection error"


def test_stats_timeseries_contract_and_reconciliation():
    db = next(get_db())

    # Create distinct Workspace and ApiClient for isolated timeseries calculation
    from app.models.api_client import ApiClient
    from app.models.workspace import Workspace
    import hashlib
    iso_ws = Workspace(name=f"TSWS_{uuid.uuid4().hex[:6]}", slug=f"tsws-{uuid.uuid4().hex[:6]}")
    db.add(iso_ws)
    db.commit()
    db.refresh(iso_ws)

    raw_key = "nk_live_" + uuid.uuid4().hex
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    client_rec = ApiClient(
        workspace_id=iso_ws.id,
        name=f"TSClient_{uuid.uuid4().hex[:8]}",
        key_hash=key_hash,
        key_prefix=raw_key[:12],
        is_active=True,
    )
    db.add(client_rec)
    db.commit()
    db.refresh(client_rec)
    c_headers = {"X-API-Key": raw_key}

    # 1. Empty timeseries
    resp_empty = client.get("/stats/timeseries?window_hours=4&bucket_hours=1", headers=c_headers)
    assert resp_empty.status_code == 200
    buckets_empty = resp_empty.json()
    assert len(buckets_empty) >= 4
    for b in buckets_empty:
        assert set(b.keys()) == {"bucket", "ok", "failed", "other"}
        assert "total" not in b
        assert "sent" not in b
        assert b["ok"] == 0
        assert b["failed"] == 0
        assert b["other"] == 0

    # 2. Add notifications: 2 ok (sent, delivered), 1 failed, 1 other (pending)
    now = datetime.now(timezone.utc)
    n_sent = Notification(workspace_id=iso_ws.id, channel="email", recipient="r1@example.com", status="sent", client_id=client_rec.id, created_at=now)
    n_deliv = Notification(workspace_id=iso_ws.id, channel="email", recipient="r2@example.com", status="delivered", client_id=client_rec.id, created_at=now)
    n_fail = Notification(workspace_id=iso_ws.id, channel="email", recipient="r3@example.com", status="failed", client_id=client_rec.id, created_at=now)
    n_pend = Notification(workspace_id=iso_ws.id, channel="email", recipient="r4@example.com", status="pending", client_id=client_rec.id, created_at=now)
    db.add_all([n_sent, n_deliv, n_fail, n_pend])
    db.commit()

    resp_pop = client.get("/stats/timeseries?window_hours=4&bucket_hours=1", headers=c_headers)
    assert resp_pop.status_code == 200
    buckets_pop = resp_pop.json()

    total_ok = sum(b["ok"] for b in buckets_pop)
    total_failed = sum(b["failed"] for b in buckets_pop)
    total_other = sum(b["other"] for b in buckets_pop)

    # Assert mutually exclusive counts reconcile with the 4 created notifications
    assert total_ok == 2
    assert total_failed == 1
    assert total_other == 1
    assert (total_ok + total_failed + total_other) == 4

    for b in buckets_pop:
        assert set(b.keys()) == {"bucket", "ok", "failed", "other"}
        assert (b["ok"] + b["failed"] + b["other"]) in (0, 4)
