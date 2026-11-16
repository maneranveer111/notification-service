import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models.delivery_event import DeliveryEvent
from app.models.notification import Notification
from app.tasks.notification_tasks import requeue_stale


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. Brevo Webhook Tests
# ---------------------------------------------------------------------------

def test_brevo_webhook_auth_failure(client):
    with patch("app.api.webhooks.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            webhook_verify=True,
            webhook_secret="correct-secret",
        )
        # Missing auth
        res1 = client.post("/webhooks/brevo", json={"event": "delivered"})
        assert res1.status_code == 401

        # Wrong bearer token
        res2 = client.post(
            "/webhooks/brevo",
            json={"event": "delivered"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
        assert res2.status_code == 401

        # Wrong query param token
        res3 = client.post(
            "/webhooks/brevo?token=wrong-secret",
            json={"event": "delivered"},
        )
        assert res3.status_code == 401


def test_brevo_webhook_delivered(client, db_session):
    msg_id = f"brevo-{uuid.uuid4()}"
    notif = Notification(
        id=uuid.uuid4(),
        channel="email",
        recipient="user@example.com",
        status="sent",
        provider_message_id=f"<{msg_id}>",
    )
    db_session.add(notif)
    db_session.commit()

    with patch("app.api.webhooks.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            webhook_verify=True,
            webhook_secret="test-secret",
        )
        res = client.post(
            "/webhooks/brevo",
            json={"event": "delivered", "message-id": msg_id},
            headers={"Authorization": "Bearer test-secret"},
        )
        assert res.status_code == 200

    db_session.refresh(notif)
    assert notif.status == "delivered"
    assert notif.delivered_at is not None

    event = db_session.execute(
        select(DeliveryEvent).where(DeliveryEvent.notification_id == notif.id)
    ).scalars().first()
    assert event is not None
    assert event.event_type == "delivered"
    assert event.provider == "brevo"


def test_brevo_webhook_hard_bounce(client, db_session):
    msg_id = f"brevo-bounce-{uuid.uuid4()}"
    notif = Notification(
        id=uuid.uuid4(),
        channel="email",
        recipient="bounced@example.com",
        status="sent",
        provider_message_id=msg_id,
    )
    db_session.add(notif)
    db_session.commit()

    with patch("app.api.webhooks.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            webhook_verify=False,
            webhook_secret=None,
        )
        res = client.post(
            "/webhooks/brevo",
            json={"event": "hard_bounce", "message-id": msg_id},
        )
        assert res.status_code == 200

    db_session.refresh(notif)
    assert notif.status == "bounced"


def test_brevo_webhook_unknown_message_id(client, db_session):
    unknown_id = f"unknown-{uuid.uuid4()}"
    with patch("app.api.webhooks.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            webhook_verify=False,
            webhook_secret=None,
        )
        res = client.post(
            "/webhooks/brevo",
            json={"event": "delivered", "message-id": unknown_id},
        )
        assert res.status_code == 200

    event = db_session.execute(
        select(DeliveryEvent).where(
            DeliveryEvent.payload["message-id"].as_string() == unknown_id
        )
    ).scalars().first()
    assert event is not None
    assert event.notification_id is None
    assert event.provider == "brevo"


# ---------------------------------------------------------------------------
# 2. Never Overwrites Terminal Statuses
# ---------------------------------------------------------------------------

def test_never_overwrites_failed(client, db_session):
    msg_id = f"failed-test-{uuid.uuid4()}"
    notif = Notification(
        id=uuid.uuid4(),
        channel="email",
        recipient="user@example.com",
        status="failed",
        error_message="Original failure reason",
        provider_message_id=msg_id,
    )
    db_session.add(notif)
    db_session.commit()

    with patch("app.api.webhooks.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(webhook_verify=False)
        res = client.post(
            "/webhooks/brevo",
            json={"event": "delivered", "message-id": msg_id},
        )
        assert res.status_code == 200

    db_session.refresh(notif)
    assert notif.status == "failed"
    assert notif.error_message == "Original failure reason"


def test_never_overwrites_delivered(client, db_session):
    msg_id = f"delivered-test-{uuid.uuid4()}"
    fixed_delivered_at = datetime.now(timezone.utc) - timedelta(hours=1)
    notif = Notification(
        id=uuid.uuid4(),
        channel="email",
        recipient="user@example.com",
        status="delivered",
        delivered_at=fixed_delivered_at,
        provider_message_id=msg_id,
    )
    db_session.add(notif)
    db_session.commit()

    with patch("app.api.webhooks.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(webhook_verify=False)
        res = client.post(
            "/webhooks/brevo",
            json={"event": "hard_bounce", "message-id": msg_id},
        )
        assert res.status_code == 200

    db_session.refresh(notif)
    assert notif.status == "delivered"


# ---------------------------------------------------------------------------
# 3. Twilio Webhook Tests
# ---------------------------------------------------------------------------

def test_twilio_webhook_bad_signature(client):
    with patch("app.api.webhooks.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            webhook_verify=True,
            public_base_url="http://localhost:8001",
            twilio_auth_token="dummy-auth-token",
        )
        res = client.post(
            "/webhooks/twilio",
            data={"MessageSid": "SM123", "MessageStatus": "delivered"},
            headers={"X-Twilio-Signature": "invalid-signature"},
        )
        assert res.status_code == 403


def test_twilio_webhook_undelivered_with_error(client, db_session):
    sid = f"SM{uuid.uuid4().hex}"
    notif = Notification(
        id=uuid.uuid4(),
        channel="sms",
        recipient="+1234567890",
        status="sent",
        provider_message_id=sid,
    )
    db_session.add(notif)
    db_session.commit()

    with patch("app.api.webhooks.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            webhook_verify=False,
            public_base_url="http://localhost:8001",
        )
        res = client.post(
            "/webhooks/twilio",
            data={
                "MessageSid": sid,
                "MessageStatus": "undelivered",
                "ErrorCode": "30008",
            },
        )
        assert res.status_code == 200

    db_session.refresh(notif)
    assert notif.status == "undelivered"
    assert "Twilio error 30008" in notif.error_message


# ---------------------------------------------------------------------------
# 4. Sweeper (Celery Beat) Tests
# ---------------------------------------------------------------------------

def test_sweeper_stale_vs_fresh(db_session):
    now = datetime.now(timezone.utc)

    stale_notif = Notification(
        id=uuid.uuid4(),
        channel="email",
        recipient="stale@example.com",
        status="pending",
        updated_at=now - timedelta(minutes=10),
    )
    fresh_notif = Notification(
        id=uuid.uuid4(),
        channel="email",
        recipient="fresh@example.com",
        status="pending",
        updated_at=now - timedelta(minutes=1),
    )
    db_session.add_all([stale_notif, fresh_notif])
    db_session.commit()

    with patch("app.tasks.notification_tasks.send_email_task.delay") as mock_email_delay, \
         patch("app.tasks.notification_tasks.send_sms_task.delay") as mock_sms_delay:
        res = requeue_stale()
        assert res["status"] == "ok"
        assert res["requeued_count"] >= 1

        mock_email_delay.assert_any_call(str(stale_notif.id))
        fresh_ids_called = [args[0] for args, _ in mock_email_delay.call_args_list]
        assert str(fresh_notif.id) not in fresh_ids_called
