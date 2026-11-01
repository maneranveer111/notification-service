import hashlib
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.main import app
from app.models.api_client import ApiClient
from app.models.notification import Notification

client = TestClient(app)
settings = get_settings()
ADMIN_HEADERS = {"X-API-Key": settings.api_key}


@pytest.fixture(autouse=True)
def mock_tasks():
    limiter.reset()
    with patch("app.api.notifications.send_email_task.delay") as m1, \
         patch("app.api.notifications.send_sms_task.delay") as m2:
        yield m1, m2
    limiter.reset()


def _create_test_client(name: str, rate_limit: int = 60) -> tuple[dict, str]:
    resp = client.post(
        "/admin/clients",
        headers=ADMIN_HEADERS,
        json={"name": name, "rate_limit_per_minute": rate_limit},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data, data["api_key"]


def test_master_key_works():
    resp = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "master@example.com",
            "subject": "Hello Master",
            "body": "Master body content",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_client_key_works():
    _, api_key = _create_test_client(f"client_{uuid.uuid4().hex[:8]}")
    resp = client.post(
        "/notifications/email",
        headers={"X-API-Key": api_key},
        json={
            "recipient": "client@example.com",
            "subject": "Hello Client",
            "body": "Client body content",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_revoked_key_returns_401():
    client_data, api_key = _create_test_client(f"client_rev_{uuid.uuid4().hex[:8]}")
    revoke_resp = client.post(
        f"/admin/clients/{client_data['id']}/revoke",
        headers=ADMIN_HEADERS,
    )
    assert revoke_resp.status_code == 200

    resp = client.post(
        "/notifications/email",
        headers={"X-API-Key": api_key},
        json={
            "recipient": "revoked@example.com",
            "subject": "Subject",
            "body": "Body",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key."


def test_unknown_key_returns_401():
    resp = client.post(
        "/notifications/email",
        headers={"X-API-Key": "nk_live_completely_unknown_key_value"},
        json={
            "recipient": "unknown@example.com",
            "subject": "Subject",
            "body": "Body",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key."


def test_client_over_limit_returns_429(monkeypatch):
    _, api_key = _create_test_client(f"client_limit_{uuid.uuid4().hex[:8]}")

    monkeypatch.setattr("app.security.check_rate_limit", lambda client_id, limit: False)

    resp = client.post(
        "/notifications/email",
        headers={"X-API-Key": api_key},
        json={
            "recipient": "overlimit@example.com",
            "subject": "Subject",
            "body": "Body",
        },
    )
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "60"
    data = resp.json()
    assert data["detail"] == "Rate limit exceeded. Try again later."
    assert data["limit"] == "60/minute"
    assert data["retry_after"] == "60 seconds"


def test_client_ownership_scoping():
    client_a_data, key_a = _create_test_client(f"client_a_{uuid.uuid4().hex[:8]}")
    client_b_data, key_b = _create_test_client(f"client_b_{uuid.uuid4().hex[:8]}")

    # Move client B to a distinct workspace to test workspace isolation
    db = next(get_db())
    from app.models.workspace import Workspace
    ws_b = Workspace(name="WS B", slug=f"ws-b-{uuid.uuid4().hex[:6]}")
    db.add(ws_b)
    db.commit()
    db.refresh(ws_b)

    client_b_row = db.get(ApiClient, client_b_data["id"])
    client_b_row.workspace_id = ws_b.id
    db.commit()

    create_resp = client.post(
        "/notifications/email",
        headers={"X-API-Key": key_a},
        json={
            "recipient": "user_a@example.com",
            "subject": "Private Subject",
            "body": "Private Content",
        },
    )
    assert create_resp.status_code == 200
    notif_id = create_resp.json()["id"]

    # Client B cannot view Client A's notification
    resp_b = client.get(f"/notifications/{notif_id}", headers={"X-API-Key": key_b})
    assert resp_b.status_code == 404

    # Admin can view it
    resp_admin = client.get(f"/notifications/{notif_id}", headers=ADMIN_HEADERS)
    assert resp_admin.status_code == 200
    assert resp_admin.json()["id"] == notif_id


def test_client_key_on_admin_endpoint_returns_403():
    _, api_key = _create_test_client(f"client_adm_{uuid.uuid4().hex[:8]}")
    resp = client.get("/admin/clients", headers={"X-API-Key": api_key})
    assert resp.status_code == 403


def test_plaintext_key_only_at_create_rotate_db_stores_hash():
    name = f"client_hash_{uuid.uuid4().hex[:8]}"
    create_data, raw_key = _create_test_client(name)
    assert "api_key" in create_data

    # Check database
    db = next(get_db())
    client_row = db.execute(select(ApiClient).where(ApiClient.id == create_data["id"])).scalar_one()
    expected_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    assert client_row.key_hash == expected_hash
    assert raw_key != client_row.key_hash

    # Check GET /admin/clients does not leak hash or key
    list_resp = client.get("/admin/clients", headers=ADMIN_HEADERS)
    assert list_resp.status_code == 200
    items = list_resp.json()
    matched = next(item for item in items if item["id"] == create_data["id"])
    assert "api_key" not in matched
    assert "key_hash" not in matched
    assert matched["key_prefix"] == raw_key[:12]

    # Rotate key
    rotate_resp = client.post(f"/admin/clients/{create_data['id']}/rotate", headers=ADMIN_HEADERS)
    assert rotate_resp.status_code == 200
    new_raw_key = rotate_resp.json()["api_key"]
    assert new_raw_key != raw_key

    db.refresh(client_row)
    assert client_row.key_hash == hashlib.sha256(new_raw_key.encode("utf-8")).hexdigest()


def test_same_idempotency_key_two_clients_creates_two_rows():
    client_a_data, key_a = _create_test_client(f"idemp_a_{uuid.uuid4().hex[:8]}")
    client_b_data, key_b = _create_test_client(f"idemp_b_{uuid.uuid4().hex[:8]}")

    # Move client B to a distinct workspace
    db = next(get_db())
    from app.models.workspace import Workspace
    ws_b = Workspace(name="WS B Idem", slug=f"ws-b-idem-{uuid.uuid4().hex[:6]}")
    db.add(ws_b)
    db.commit()
    db.refresh(ws_b)

    client_b_row = db.get(ApiClient, client_b_data["id"])
    client_b_row.workspace_id = ws_b.id
    db.commit()

    idem_key = f"shared-idem-key-{uuid.uuid4().hex[:6]}"

    resp_a = client.post(
        "/notifications/email",
        headers={"X-API-Key": key_a, "Idempotency-Key": idem_key},
        json={"recipient": "user@example.com", "subject": "Subj", "body": "Body"},
    )
    assert resp_a.status_code == 200
    id_a = resp_a.json()["id"]

    resp_b = client.post(
        "/notifications/email",
        headers={"X-API-Key": key_b, "Idempotency-Key": idem_key},
        json={"recipient": "user@example.com", "subject": "Subj", "body": "Body"},
    )
    assert resp_b.status_code == 200
    id_b = resp_b.json()["id"]

    assert id_a != id_b


def test_template_renders_and_stores_rendered_text():
    tpl_resp = client.post(
        "/templates",
        headers=ADMIN_HEADERS,
        json={
            "name": "Welcome Email",
            "channel": "email",
            "subject_template": "Welcome {{ name }}!",
            "body_template": "Hello {{ name }}, welcome to {{ team }}.",
        },
    )
    assert tpl_resp.status_code == 201
    tpl = tpl_resp.json()
    assert "name" in tpl["variables"]
    assert "team" in tpl["variables"]

    queue_resp = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "alice@example.com",
            "template_id": tpl["id"],
            "variables": {"name": "Alice", "team": "Platform"},
        },
    )
    assert queue_resp.status_code == 200
    notif_id = queue_resp.json()["id"]

    get_resp = client.get(f"/notifications/{notif_id}", headers=ADMIN_HEADERS)
    assert get_resp.status_code == 200
    notif_data = get_resp.json()
    assert notif_data["subject"] == "Welcome Alice!"
    assert notif_data["body"] == "Hello Alice, welcome to Platform."
    assert notif_data["template_id"] == tpl["id"]


def test_missing_variable_returns_422():
    tpl_resp = client.post(
        "/templates",
        headers=ADMIN_HEADERS,
        json={
            "name": "Alert",
            "channel": "email",
            "subject_template": "Alert: {{ title }}",
            "body_template": "Severity: {{ severity }}",
        },
    )
    assert tpl_resp.status_code == 201
    tpl_id = tpl_resp.json()["id"]

    resp = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "bob@example.com",
            "template_id": tpl_id,
            "variables": {"title": "Outage"},  # missing 'severity'
        },
    )
    assert resp.status_code == 422
    assert "severity" in resp.json()["detail"]


def test_template_and_body_together_returns_422():
    tpl_resp = client.post(
        "/templates",
        headers=ADMIN_HEADERS,
        json={
            "name": "Simple",
            "channel": "email",
            "subject_template": "Subj",
            "body_template": "Body",
        },
    )
    assert tpl_resp.status_code == 201
    tpl_id = tpl_resp.json()["id"]

    resp = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "bob@example.com",
            "template_id": tpl_id,
            "body": "Extra body",
        },
    )
    assert resp.status_code == 422


def test_channel_mismatch_returns_422():
    tpl_resp = client.post(
        "/templates",
        headers=ADMIN_HEADERS,
        json={
            "name": "SMS Template",
            "channel": "sms",
            "body_template": "Code: {{ code }}",
        },
    )
    assert tpl_resp.status_code == 201
    tpl_id = tpl_resp.json()["id"]

    resp = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "bob@example.com",
            "template_id": tpl_id,
            "variables": {"code": "1234"},
        },
    )
    assert resp.status_code == 422
    assert "channel" in resp.json()["detail"].lower()

