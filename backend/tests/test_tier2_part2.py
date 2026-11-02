from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.main import app
from app.models.api_client import ApiClient
from app.models.notification import Notification
from app.tasks.notification_tasks import dispatch_scheduled, send_email_task, send_sms_task

client = TestClient(app)
settings = get_settings()
ADMIN_HEADERS = {"X-API-Key": settings.api_key}


@pytest.fixture(autouse=True)
def mock_tasks():
    limiter.reset()
    with patch.object(send_email_task, "apply_async", return_value=MagicMock()) as m_email, \
         patch.object(send_sms_task, "apply_async", return_value=MagicMock()) as m_sms:
        yield m_email, m_sms
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


def test_scheduled_request_stored_as_scheduled_and_not_enqueued(mock_tasks):
    m_email, _ = mock_tasks
    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    resp = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "sched@example.com",
            "subject": "Scheduled email",
            "body": "Body content",
            "scheduled_at": future_time,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "scheduled"
    m_email.assert_not_called()

    get_resp = client.get(f"/notifications/{data['id']}", headers=ADMIN_HEADERS)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "scheduled"
    assert get_resp.json()["scheduled_at"] is not None


def test_invalid_scheduled_at_returns_422():
    # 1. Past scheduled_at
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    resp1 = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "past@example.com",
            "subject": "Past email",
            "body": "Body content",
            "scheduled_at": past_time,
        },
    )
    assert resp1.status_code == 422
    assert "future" in resp1.json()["detail"].lower()

    # 2. More than 30 days in future
    far_future = (datetime.now(timezone.utc) + timedelta(days=35)).isoformat()
    resp2 = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "future@example.com",
            "subject": "Far future email",
            "body": "Body content",
            "scheduled_at": far_future,
        },
    )
    assert resp2.status_code == 422
    assert "30" in resp2.json()["detail"]

    # 3. Timezone-naive datetime
    naive_time = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
    resp3 = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "naive@example.com",
            "subject": "Naive email",
            "body": "Body content",
            "scheduled_at": naive_time,
        },
    )
    assert resp3.status_code == 422
    assert "timezone-aware" in resp3.json()["detail"].lower()


def test_dispatch_scheduled_task(mock_tasks):
    m_email, _ = mock_tasks
    db = next(get_db())

    now = datetime.now(timezone.utc)
    # Insert due notification
    due_notif = Notification(
        channel="email",
        recipient="due@example.com",
        subject="Due",
        body="Content",
        status="scheduled",
        scheduled_at=now - timedelta(minutes=5),
        priority="normal",
    )
    # Insert future notification
    future_notif = Notification(
        channel="email",
        recipient="future@example.com",
        subject="Future",
        body="Content",
        status="scheduled",
        scheduled_at=now + timedelta(hours=2),
        priority="normal",
    )
    db.add(due_notif)
    db.add(future_notif)
    db.commit()
    db.refresh(due_notif)
    db.refresh(future_notif)

    # Run dispatch_scheduled
    res = dispatch_scheduled()
    assert res["status"] == "ok"
    assert res["dispatched_count"] >= 1

    db.refresh(due_notif)
    db.refresh(future_notif)
    assert due_notif.status == "pending"
    assert future_notif.status == "scheduled"
    assert m_email.call_count >= 1


def test_cancel_scheduled_notification():
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    resp = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "cancel@example.com",
            "subject": "To Cancel",
            "body": "Body",
            "scheduled_at": future_time,
        },
    )
    notif_id = resp.json()["id"]

    cancel_resp = client.post(f"/notifications/{notif_id}/cancel", headers=ADMIN_HEADERS)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_cancel_non_scheduled_notification_returns_409():
    resp = client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "instant@example.com",
            "subject": "Instant",
            "body": "Body",
        },
    )
    notif_id = resp.json()["id"]

    cancel_resp = client.post(f"/notifications/{notif_id}/cancel", headers=ADMIN_HEADERS)
    assert cancel_resp.status_code == 409
    assert "pending" in cancel_resp.json()["detail"].lower()


def test_cancel_unknown_or_other_client_returns_404():
    client_a_data, key_a = _create_test_client(f"client_a_{uuid.uuid4().hex[:8]}")
    client_b_data, key_b = _create_test_client(f"client_b_{uuid.uuid4().hex[:8]}")

    # Move client B to a distinct workspace
    db = next(get_db())
    import secrets
    from app.models.workspace import Workspace
    ws_b = Workspace(name="WS B Cancel", slug=f"ws-b-cancel-{uuid.uuid4().hex[:6]}", webhook_token=secrets.token_urlsafe(32))
    db.add(ws_b)
    db.commit()
    db.refresh(ws_b)
    client_b_row = db.get(ApiClient, client_b_data["id"])
    client_b_row.workspace_id = ws_b.id
    db.commit()

    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    resp = client.post(
        "/notifications/email",
        headers={"X-API-Key": key_a},
        json={
            "recipient": "user@example.com",
            "subject": "Subject",
            "body": "Body",
            "scheduled_at": future_time,
        },
    )
    notif_id = resp.json()["id"]

    # Client B cannot cancel Client A's notification
    cancel_b = client.post(f"/notifications/{notif_id}/cancel", headers={"X-API-Key": key_b})
    assert cancel_b.status_code == 404

    # Unknown notification ID -> 404
    unknown_id = str(uuid.uuid4())
    cancel_unknown = client.post(f"/notifications/{unknown_id}/cancel", headers=ADMIN_HEADERS)
    assert cancel_unknown.status_code == 404


def test_priority_queues(mock_tasks):
    m_email, _ = mock_tasks

    # High priority
    client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "high@example.com",
            "subject": "High",
            "body": "Body",
            "priority": "high",
        },
    )
    assert m_email.call_count == 1
    _, kwargs = m_email.call_args
    assert kwargs.get("queue") == f"{settings.celery_queue}_high"

    # Low priority
    client.post(
        "/notifications/email",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "low@example.com",
            "subject": "Low",
            "body": "Body",
            "priority": "low",
        },
    )
    assert m_email.call_count == 2
    _, kwargs = m_email.call_args
    assert kwargs.get("queue") == f"{settings.celery_queue}_low"


def test_bulk_send_creates_rows_and_deduplicates(mock_tasks):
    m_email, _ = mock_tasks
    recipients = [
        {"recipient": "user1@example.com"},
        {"recipient": "USER1@example.com"},  # case-insensitive duplicate
        {"recipient": "user2@example.com"},
    ]

    resp = client.post(
        "/notifications/bulk",
        headers=ADMIN_HEADERS,
        json={
            "channel": "email",
            "recipients": recipients,
            "subject": "Bulk Subject",
            "body": "Bulk Body",
            "priority": "high",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["queued"] == 2
    assert len(data["ids"]) == 2
    assert data["batch_id"] is not None

    assert m_email.call_count == 2
    _, kwargs = m_email.call_args
    assert kwargs.get("queue") == f"{settings.celery_queue}_high"


def test_bulk_over_limit_returns_422():
    recipients = [{"recipient": f"user{i}@example.com"} for i in range(205)]
    resp = client.post(
        "/notifications/bulk",
        headers=ADMIN_HEADERS,
        json={
            "channel": "email",
            "recipients": recipients,
            "subject": "Subject",
            "body": "Body",
        },
    )
    assert resp.status_code == 422
    assert "exceeds maximum" in resp.json()["detail"].lower()


def test_batch_status_counts():
    recipients = [
        {"recipient": f"batch1_{uuid.uuid4().hex[:6]}@example.com"},
        {"recipient": f"batch2_{uuid.uuid4().hex[:6]}@example.com"},
    ]

    resp = client.post(
        "/notifications/bulk",
        headers=ADMIN_HEADERS,
        json={
            "channel": "email",
            "recipients": recipients,
            "subject": "Batch Status Test",
            "body": "Body",
        },
    )
    assert resp.status_code == 200
    batch_id = resp.json()["batch_id"]

    status_resp = client.get(f"/notifications/batches/{batch_id}", headers=ADMIN_HEADERS)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["batch_id"] == batch_id
    assert status_data["total"] == 2
    assert status_data["counts_by_status"]["pending"] == 2


def test_batch_scoping_other_client_returns_404():
    client_a_data, key_a = _create_test_client(f"client_batch_a_{uuid.uuid4().hex[:8]}")
    client_b_data, key_b = _create_test_client(f"client_batch_b_{uuid.uuid4().hex[:8]}")

    # Move client B to a distinct workspace
    db = next(get_db())
    import secrets
    from app.models.workspace import Workspace
    ws_b = Workspace(name="WS B Batch", slug=f"ws-b-batch-{uuid.uuid4().hex[:6]}", webhook_token=secrets.token_urlsafe(32))
    db.add(ws_b)
    db.commit()
    db.refresh(ws_b)
    client_b_row = db.get(ApiClient, client_b_data["id"])
    client_b_row.workspace_id = ws_b.id
    db.commit()

    resp = client.post(
        "/notifications/bulk",
        headers={"X-API-Key": key_a},
        json={
            "channel": "email",
            "recipients": [{"recipient": "scoped@example.com"}],
            "subject": "Subject",
            "body": "Body",
        },
    )
    assert resp.status_code == 200
    batch_id = resp.json()["batch_id"]

    # Client B cannot view Client A's batch
    resp_b = client.get(f"/notifications/batches/{batch_id}", headers={"X-API-Key": key_b})
    assert resp_b.status_code == 404

    # Admin can view it
    resp_admin = client.get(f"/notifications/batches/{batch_id}", headers=ADMIN_HEADERS)
    assert resp_admin.status_code == 200
    assert resp_admin.json()["total"] == 1

