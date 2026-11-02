"""
Tier 4C2 tests: Plans/Quotas, Resource Limits, GET /usage, and Turnstile CAPTCHA.
"""
import contextlib
from datetime import datetime, timezone
import secrets
from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient
import requests
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.api_client import ApiClient
from app.models.invitation import Invitation
from app.models.notification import Notification
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password
from app.services.plans import PLANS, get_effective_bulk_max, get_plan
from app.services.quota import QuotaExceeded, consume_quota, get_usage, release_quota
from app.services.rate_limit import get_redis_client
from app.services.tenancy import generate_workspace_slug, get_default_workspace
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


def _create_workspace(db, name="Test WS", plan="free", use_platform_providers=True):
    slug = f"ws-{uuid.uuid4().hex[:8]}"
    ws = Workspace(
        name=name,
        slug=slug,
        plan=plan,
        use_platform_providers=use_platform_providers,
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
# 1. Plans & Migration Tests
# ---------------------------------------------------------------------------

def test_plan_dict_structure():
    assert "free" in PLANS
    assert "pro" in PLANS
    assert "unlimited" in PLANS
    assert PLANS["free"]["daily"] == 100
    assert PLANS["free"]["monthly"] == 3000
    assert PLANS["pro"]["daily"] == 5000
    assert PLANS["pro"]["monthly"] == 100000
    for k in ("daily", "monthly", "bulk_max", "api_keys", "members"):
        assert PLANS["unlimited"][k] is None


def test_effective_bulk_max():
    with _settings_override(bulk_max_recipients=200):
        assert get_effective_bulk_max("free") == 100
        assert get_effective_bulk_max("pro") == 200
        assert get_effective_bulk_max("unlimited") == 200

    with _settings_override(bulk_max_recipients=50):
        assert get_effective_bulk_max("free") == 50
        assert get_effective_bulk_max("pro") == 50
        assert get_effective_bulk_max("unlimited") == 50


def test_default_workspace_is_unlimited(db):
    default_ws = get_default_workspace(db)
    assert default_ws.plan == "unlimited"


def test_new_workspace_defaults_to_free(db):
    ws = _create_workspace(db, plan="free")
    assert ws.plan == "free"


def test_admin_workspaces_patch_plan(db):
    superadmin = _make_user(db, is_superadmin=True)
    ws = _create_workspace(db, plan="free")
    _add_member(db, superadmin, ws, "owner")
    h = _auth_headers(superadmin, ws.id)

    # Valid plan update
    resp = client.patch(f"/admin/workspaces/{ws.id}", headers=h, json={"plan": "pro"})
    assert resp.status_code == 200
    assert resp.json()["plan"] == "pro"

    # Verify GET /admin/workspaces includes plan
    resp_list = client.get("/admin/workspaces", headers=h)
    assert resp_list.status_code == 200
    matching = [w for w in resp_list.json() if w["id"] == str(ws.id)]
    assert matching[0]["plan"] == "pro"

    # Invalid plan -> 422
    resp_invalid = client.patch(f"/admin/workspaces/{ws.id}", headers=h, json={"plan": "mega_enterprise"})
    assert resp_invalid.status_code == 422

    # Non-superadmin forbidden
    user = _make_user(db, is_superadmin=False)
    _add_member(db, user, ws, "admin")
    h_user = _auth_headers(user, ws.id)
    resp_forbid = client.patch(f"/admin/workspaces/{ws.id}", headers=h_user, json={"plan": "free"})
    assert resp_forbid.status_code == 403


# ---------------------------------------------------------------------------
# 2. Sending Quotas Tests
# ---------------------------------------------------------------------------

def test_quota_daily_limit_exceeded_and_atomic_rollback(db):
    ws = _create_workspace(db, plan="free")
    now = datetime.now(timezone.utc)
    key_d = f"quota:{ws.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{ws.id}:m:{now.strftime('%Y%m')}"
    r = get_redis_client()
    r.delete(key_d, key_m)

    # Free plan daily limit is 100
    consume_quota(ws, 100)
    assert int(r.get(key_d) or 0) == 100
    assert int(r.get(key_m) or 0) == 100

    # Consuming 1 more exceeds limit -> raises QuotaExceeded
    with pytest.raises(QuotaExceeded) as exc_info:
        consume_quota(ws, 1)
    assert exc_info.value.scope == "daily"
    assert exc_info.value.limit == 100

    # Ensure atomic rollback: counters remain at 100, not 101
    assert int(r.get(key_d) or 0) == 100
    assert int(r.get(key_m) or 0) == 100

    # Release quota decrements
    release_quota(ws, 10)
    assert int(r.get(key_d) or 0) == 90
    assert int(r.get(key_m) or 0) == 90
    r.delete(key_d, key_m)


def test_quota_monthly_limit_exceeded(db):
    ws = _create_workspace(db, plan="free")
    now = datetime.now(timezone.utc)
    key_d = f"quota:{ws.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{ws.id}:m:{now.strftime('%Y%m')}"
    r = get_redis_client()
    r.delete(key_d, key_m)

    # Set monthly counter right at monthly limit (3000)
    r.set(key_m, 3000)
    # Daily is 0
    with pytest.raises(QuotaExceeded) as exc_info:
        consume_quota(ws, 1)
    assert exc_info.value.scope == "monthly"
    assert exc_info.value.limit == 3000

    # Daily counter should have been rolled back to 0
    assert int(r.get(key_d) or 0) == 0
    r.delete(key_d, key_m)


def test_quota_disabled_bypasses_check(db):
    ws = _create_workspace(db, plan="free")
    with _settings_override(quota_enabled=False):
        # Even with n > 100, nothing raises or tracks
        consume_quota(ws, 500)


def test_quota_redis_down_fails_open(db):
    ws = _create_workspace(db, plan="free")
    with patch("app.services.quota.get_redis_client", side_effect=Exception("Redis connection refused")):
        # Must fail open (not raise QuotaExceeded)
        consume_quota(ws, 1)


def test_notification_creation_429_on_quota_exceeded(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="free", use_platform_providers=True)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # Fill daily quota to max
    now = datetime.now(timezone.utc)
    key_d = f"quota:{ws.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{ws.id}:m:{now.strftime('%Y%m')}"
    r = get_redis_client()
    r.set(key_d, 100)
    r.set(key_m, 100)

    resp = client.post(
        "/notifications/email",
        headers=h,
        json={"recipient": "test@example.com", "subject": "Hi", "body": "Hello"},
    )
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") is not None
    data = resp.json()
    assert data["code"] == "quota_exceeded"
    assert data["scope"] == "daily"
    assert data["limit"] == 100
    assert "reset_at" in data

    r.delete(key_d, key_m)


def test_idempotent_replay_and_suppressed_consume_no_quota(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="free", use_platform_providers=True)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    now = datetime.now(timezone.utc)
    key_d = f"quota:{ws.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{ws.id}:m:{now.strftime('%Y%m')}"
    r = get_redis_client()
    r.delete(key_d, key_m)

    # 1. Normal send consumes 1
    idem_key = f"idem-{uuid.uuid4().hex}"
    resp1 = client.post(
        "/notifications/email",
        headers={**h, "Idempotency-Key": idem_key},
        json={"recipient": "fresh@example.com", "subject": "S", "body": "B"},
    )
    assert resp1.status_code == 200
    assert int(r.get(key_d) or 0) == 1

    # Replay consumes 0
    resp2 = client.post(
        "/notifications/email",
        headers={**h, "Idempotency-Key": idem_key},
        json={"recipient": "fresh@example.com", "subject": "S", "body": "B"},
    )
    assert resp2.status_code == 200
    assert resp2.headers.get("Idempotent-Replay") == "true"
    assert int(r.get(key_d) or 0) == 1

    # 2. Add suppression
    client.post("/suppressions", headers=h, json={"channel": "email", "recipient": "blocked@example.com", "reason": "bounce"})

    # Send to suppressed recipient consumes 0 quota
    resp_sup = client.post(
        "/notifications/email",
        headers=h,
        json={"recipient": "blocked@example.com", "subject": "S", "body": "B"},
    )
    assert resp_sup.status_code == 200
    assert resp_sup.json()["status"] == "suppressed"
    assert int(r.get(key_d) or 0) == 1  # still 1!

    r.delete(key_d, key_m)


def test_bulk_all_or_nothing_and_release_quota_on_failure(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="free", use_platform_providers=True)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    now = datetime.now(timezone.utc)
    key_d = f"quota:{ws.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{ws.id}:m:{now.strftime('%Y%m')}"
    r = get_redis_client()
    r.delete(key_d, key_m)

    # Free plan has 100 limit; set daily counter to 98
    r.set(key_d, 98)
    r.set(key_m, 98)

    # Attempt to bulk send 3 items (98 + 3 = 101 > 100) -> 429
    resp = client.post(
        "/notifications/bulk",
        headers=h,
        json={
            "channel": "email",
            "subject": "Subj",
            "body": "Body",
            "recipients": [
                {"recipient": "a@example.com"},
                {"recipient": "b@example.com"},
                {"recipient": "c@example.com"},
            ],
        },
    )
    assert resp.status_code == 429
    # Counter must remain at 98 (atomic rollback)
    assert int(r.get(key_d) or 0) == 98

    # Failure during bulk releases quota
    r.set(key_d, 5)
    r.set(key_m, 5)
    release_quota(ws, 5)
    assert int(r.get(key_d) or 0) == 0
    assert int(r.get(key_m) or 0) == 0

    r.delete(key_d, key_m)


def test_scheduled_notification_counted_at_creation(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="free", use_platform_providers=True)
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    now = datetime.now(timezone.utc)
    key_d = f"quota:{ws.id}:d:{now.strftime('%Y%m%d')}"
    r = get_redis_client()
    r.delete(key_d)

    future_iso = "2026-11-10T12:00:00Z"
    resp = client.post(
        "/notifications/email",
        headers=h,
        json={"recipient": "sched@example.com", "subject": "S", "body": "B", "scheduled_at": future_iso},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "scheduled"
    assert int(r.get(key_d) or 0) == 1

    r.delete(key_d)


def test_workspace_isolation_quota(db):
    user_a = _make_user(db)
    ws_a = _create_workspace(db, name="WS A", plan="free", use_platform_providers=True)
    _add_member(db, user_a, ws_a, "owner")
    h_a = _auth_headers(user_a, ws_a.id)

    user_b = _make_user(db)
    ws_b = _create_workspace(db, name="WS B", plan="free", use_platform_providers=True)
    _add_member(db, user_b, ws_b, "owner")
    h_b = _auth_headers(user_b, ws_b.id)

    now = datetime.now(timezone.utc)
    r = get_redis_client()
    key_a = f"quota:{ws_a.id}:d:{now.strftime('%Y%m%d')}"
    key_b = f"quota:{ws_b.id}:d:{now.strftime('%Y%m%d')}"
    r.delete(key_a, key_b)

    # Exhaust WS A's quota
    r.set(key_a, 100)

    # WS A gets 429
    resp_a = client.post("/notifications/email", headers=h_a, json={"recipient": "a@ex.com", "subject": "S", "body": "B"})
    assert resp_a.status_code == 429

    # WS B can still send freely
    resp_b = client.post("/notifications/email", headers=h_b, json={"recipient": "b@ex.com", "subject": "S", "body": "B"})
    assert resp_b.status_code == 200
    assert int(r.get(key_b) or 0) == 1

    r.delete(key_a, key_b)


# ---------------------------------------------------------------------------
# 3. Plan Limits on Other Resources (API Keys, Members, Bulk Size)
# ---------------------------------------------------------------------------

def test_api_keys_plan_limit(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="free")  # Free allows 3 api_keys
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # Create 3 keys successfully
    for i in range(3):
        resp = client.post("/admin/clients", headers=h, json={"name": f"key_{i}"})
        assert resp.status_code == 201

    # 4th key -> 403 plan_limit
    resp_4 = client.post("/admin/clients", headers=h, json={"name": "key_4"})
    assert resp_4.status_code == 403
    data = resp_4.json()
    assert data["code"] == "plan_limit"
    assert data["resource"] == "api_keys"
    assert data["limit"] == 3


def test_members_and_pending_invitations_plan_limit(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="free")  # Free allows 5 members
    _add_member(db, user, ws, "owner")  # 1 member
    h = _auth_headers(user, ws.id)

    with patch("app.api.invitations.queue_system_email"):
        # Add 3 more members via invitations: 1 member + 3 pending invites = 4 total
        for i in range(3):
            resp = client.post(
                "/workspaces/current/invitations",
                headers=h,
                json={"email": f"invite_{i}@example.com", "role": "viewer"},
            )
            assert resp.status_code == 201

        # 5th total (4th invite): total becomes 5
        resp_5 = client.post(
            "/workspaces/current/invitations",
            headers=h,
            json={"email": "invite_4@example.com", "role": "viewer"},
        )
        assert resp_5.status_code == 201

        # 6th total -> 403 plan_limit
        resp_6 = client.post(
            "/workspaces/current/invitations",
            headers=h,
            json={"email": "invite_5@example.com", "role": "viewer"},
        )
        assert resp_6.status_code == 403
        data = resp_6.json()
        assert data["code"] == "plan_limit"
        assert data["resource"] == "members"
        assert data["limit"] == 5


def test_bulk_size_plan_limit(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="free", use_platform_providers=True)  # Free allows bulk_max 100
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # 101 recipients exceeds plan limit of 100
    recipients = [{"recipient": f"r{i}@example.com"} for i in range(101)]
    resp = client.post(
        "/notifications/bulk",
        headers=h,
        json={"channel": "email", "subject": "S", "body": "B", "recipients": recipients},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["code"] == "plan_limit"
    assert data["resource"] == "bulk_recipients"
    assert data["limit"] == 100


def test_unlimited_plan_has_no_resource_limits(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="unlimited")
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # Can create more than 3 API keys without 403
    for i in range(4):
        resp = client.post("/admin/clients", headers=h, json={"name": f"unlimited_key_{i}"})
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 4. Usage Endpoint Tests
# ---------------------------------------------------------------------------

def test_get_usage_structure_and_values(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="pro")
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    now = datetime.now(timezone.utc)
    key_d = f"quota:{ws.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{ws.id}:m:{now.strftime('%Y%m')}"
    r = get_redis_client()
    r.set(key_d, 42)
    r.set(key_m, 150)

    resp = client.get("/usage", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "pro"
    assert data["daily"]["used"] == 42
    assert data["daily"]["limit"] == 5000
    assert "resets_at" in data["daily"]
    assert data["monthly"]["used"] == 150
    assert data["monthly"]["limit"] == 100000
    assert data["api_keys"]["used"] == 0
    assert data["api_keys"]["limit"] == 20
    assert data["members"]["used"] == 1  # the owner
    assert data["members"]["limit"] == 25

    r.delete(key_d, key_m)


def test_get_usage_redis_fallback_to_db(db):
    user = _make_user(db)
    ws = _create_workspace(db, plan="free")
    _add_member(db, user, ws, "owner")
    h = _auth_headers(user, ws.id)

    # Insert 2 notifications in DB for today
    notif1 = Notification(workspace_id=ws.id, channel="email", recipient="a@b.com", status="sent")
    notif2 = Notification(workspace_id=ws.id, channel="sms", recipient="+1234", status="pending")
    db.add_all([notif1, notif2])
    db.commit()

    with patch("app.services.quota.get_redis_client", side_effect=Exception("Redis down")):
        resp = client.get("/usage", headers=h)
        assert resp.status_code == 200
        data = resp.json()
        assert data["daily"]["used"] >= 2
        assert data["monthly"]["used"] >= 2


# ---------------------------------------------------------------------------
# 5. Cloudflare Turnstile CAPTCHA Tests
# ---------------------------------------------------------------------------

def test_captcha_disabled_when_secret_key_empty():
    with _settings_override(turnstile_secret_key=None, signup_mode="open"), \
         patch("app.api.accounts.queue_system_email"):
        resp = client.post("/auth/signup", json={"email": f"c_{uuid.uuid4().hex[:6]}@example.com", "password": "password123!"})
        assert resp.status_code in (201, 202)


def test_captcha_required_when_secret_key_set_missing_token():
    with _settings_override(turnstile_secret_key="secret-key-123", signup_mode="open"):
        # Missing captcha_token
        resp = client.post("/auth/signup", json={"email": "cap@example.com", "password": "password123!"})
        assert resp.status_code == 400
        assert resp.json()["code"] == "captcha_failed"


def test_captcha_failed_verification():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": False, "error-codes": ["invalid-input-response"]}

    with _settings_override(turnstile_secret_key="secret-key-123", signup_mode="open"), \
         patch("requests.post", return_value=mock_resp):
        resp = client.post(
            "/auth/signup",
            json={"email": "cap@example.com", "password": "password123!", "captcha_token": "bad-token"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "captcha_failed"


def test_captcha_network_error_returns_503_fail_closed(db):
    user_count_before = db.scalar(select(User.id).limit(1))

    with _settings_override(turnstile_secret_key="secret-key-123", signup_mode="open"), \
         patch("requests.post", side_effect=requests.RequestException("Network timeout")):
        resp = client.post(
            "/auth/signup",
            json={"email": "cap@example.com", "password": "password123!", "captcha_token": "any-token"},
        )
        assert resp.status_code == 503
        assert resp.json()["code"] == "captcha_unavailable"

    # Confirm check runs before DB work
    user_after = db.scalar(select(User).where(User.email == "cap@example.com"))
    assert user_after is None


def test_captcha_success_passes_on_all_three_routes(db):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": True}

    with _settings_override(turnstile_secret_key="secret-key-123", signup_mode="open"), \
         patch("requests.post", return_value=mock_resp), \
         patch("app.api.accounts.queue_system_email"):

        # 1. Signup
        signup_email = f"cap_ok_{uuid.uuid4().hex[:6]}@example.com"
        resp_signup = client.post(
            "/auth/signup",
            json={"email": signup_email, "password": "password123!", "captcha_token": "good-token"},
        )
        assert resp_signup.status_code in (201, 202)

        # 2. Resend verification
        resp_resend = client.post(
            "/auth/resend-verification",
            json={"email": signup_email, "captcha_token": "good-token"},
        )
        assert resp_resend.status_code == 202

        # 3. Forgot password
        resp_forgot = client.post(
            "/auth/forgot-password",
            json={"email": signup_email, "captcha_token": "good-token"},
        )
        assert resp_forgot.status_code == 202
