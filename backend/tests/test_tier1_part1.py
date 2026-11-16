import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.main import app
from app.models.notification import Notification
from app.security import verify_api_key
from app.services import email_service
from app.services.errors import PermanentError, TransientError
from app.tasks.notification_tasks import _deliver



@pytest.fixture
def client():
    app.dependency_overrides[verify_api_key] = lambda: True
    app.state.limiter.enabled = False
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.state.limiter.enabled = True


# ---------------------------------------------------------------------------
# 1. Idempotency tests (3 tests)
# ---------------------------------------------------------------------------

def test_idempotency_same_key_same_payload(client):
    key = f"key-{uuid.uuid4()}"
    payload = {
        "recipient": f"user-{uuid.uuid4()}@example.com",
        "subject": "Hello",
        "body": "World",
    }

    with patch("app.api.notifications.send_email_task.delay") as mock_delay:
        # First request
        res1 = client.post("/notifications/email", json=payload, headers={"Idempotency-Key": key})
        assert res1.status_code == 200
        data1 = res1.json()
        assert "id" in data1
        assert "Idempotent-Replay" not in res1.headers
        assert mock_delay.call_count == 1

        # Second request with same key and same payload
        res2 = client.post("/notifications/email", json=payload, headers={"Idempotency-Key": key})
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["id"] == data1["id"]
        assert res2.headers.get("Idempotent-Replay") == "true"
        # Must not enqueue again
        assert mock_delay.call_count == 1


def test_idempotency_same_key_different_payload(client):
    key = f"key-{uuid.uuid4()}"
    recipient = f"user-{uuid.uuid4()}@example.com"
    payload1 = {"recipient": recipient, "subject": "Hello", "body": "First"}
    payload2 = {"recipient": recipient, "subject": "Hello", "body": "Different body"}

    with patch("app.api.notifications.send_email_task.delay"):
        res1 = client.post("/notifications/email", json=payload1, headers={"Idempotency-Key": key})
        assert res1.status_code == 200

        res2 = client.post("/notifications/email", json=payload2, headers={"Idempotency-Key": key})
        assert res2.status_code == 422
        assert "Idempotency-Key reused with a different request" in res2.json()["detail"]


def test_idempotency_no_header_creates_multiple_rows(client):
    recipient = f"user-{uuid.uuid4()}@example.com"
    payload = {"recipient": recipient, "subject": "Hello", "body": "No header"}

    with patch("app.api.notifications.send_email_task.delay") as mock_delay:
        res1 = client.post("/notifications/email", json=payload)
        res2 = client.post("/notifications/email", json=payload)

        assert res1.status_code == 200
        assert res2.status_code == 200
        assert res1.json()["id"] != res2.json()["id"]
        assert mock_delay.call_count == 2


# ---------------------------------------------------------------------------
# 2. Email failover tests (2 tests)
# ---------------------------------------------------------------------------

def test_failover_brevo_transient_uses_smtp():
    with patch.object(email_service, "_send_brevo", side_effect=TransientError("Brevo 500")):
        with patch.object(email_service, "_send_smtp", return_value="<smtp-msg-id@example.com>") as mock_smtp:
            with patch("app.services.email_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    email_provider_order="brevo,smtp",
                    brevo_api_key="brevo-key",
                    brevo_from_email="sender@example.com",
                    smtp_host="localhost",
                    smtp_user="user",
                    smtp_password="password",
                    smtp_from_email="sender@example.com",
                )
                provider, msg_id = email_service.send_email("to@example.com", "Subject", "Body")
                assert provider == "smtp"
                assert msg_id == "<smtp-msg-id@example.com>"
                mock_smtp.assert_called_once()


def test_failover_brevo_permanent_error_no_failover():
    with patch.object(email_service, "_send_brevo", side_effect=PermanentError("400 Bad Request", failover=False)):
        with patch.object(email_service, "_send_smtp") as mock_smtp:
            with patch("app.services.email_service.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    email_provider_order="brevo,smtp",
                    brevo_api_key="brevo-key",
                    brevo_from_email="sender@example.com",
                    smtp_host="localhost",
                    smtp_user="user",
                    smtp_password="password",
                    smtp_from_email="sender@example.com",
                )
                with pytest.raises(PermanentError) as exc_info:
                    email_service.send_email("to@example.com", "Subject", "Body")
                assert "400 Bad Request" in str(exc_info.value)
                mock_smtp.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Retries and task helper tests (3 tests)
# ---------------------------------------------------------------------------

def test_retries_permanent_error_marks_failed_no_retry():
    mock_notif = Notification(
        id=uuid.uuid4(),
        channel="email",
        recipient="test@example.com",
        status="pending",
        attempt_count=0,
    )
    mock_session = MagicMock()
    mock_session.get.return_value = mock_notif
    mock_task = MagicMock()
    mock_task.request.retries = 0

    def send_fn(n):
        raise PermanentError("Permanent mailbox error", failover=False)

    with patch("app.tasks.notification_tasks.SessionLocal", return_value=mock_session):
        res = _deliver(mock_task, str(mock_notif.id), send_fn)

    assert res["status"] == "failed"
    assert mock_notif.status == "failed"
    assert "Permanent mailbox error" in mock_notif.error_message
    mock_task.retry.assert_not_called()


def test_retries_transient_error_triggers_retry_with_countdown():
    mock_notif = Notification(
        id=uuid.uuid4(),
        channel="sms",
        recipient="+14155550123",
        status="pending",
        attempt_count=0,
    )
    mock_session = MagicMock()
    mock_session.get.return_value = mock_notif
    mock_task = MagicMock()
    mock_task.request.retries = 1
    mock_task.retry.side_effect = Exception("CeleryRetryTriggered")

    def send_fn(n):
        raise TransientError("Twilio 429 rate limited")

    with patch("app.tasks.notification_tasks.SessionLocal", return_value=mock_session):
        with pytest.raises(Exception, match="CeleryRetryTriggered"):
            _deliver(mock_task, str(mock_notif.id), send_fn)

    assert mock_session.rollback.called
    assert mock_task.retry.called
    countdown = mock_task.retry.call_args.kwargs["countdown"]
    # retries = 1 -> min(600, 30 * 2^1) = 60 + (0 to 10)
    assert 60 <= countdown <= 70


def test_retries_already_sent_or_delivered_skipped():
    mock_notif = Notification(
        id=uuid.uuid4(),
        channel="email",
        recipient="test@example.com",
        status="sent",
        attempt_count=1,
    )
    mock_session = MagicMock()
    mock_session.get.return_value = mock_notif
    mock_task = MagicMock()
    mock_send = MagicMock()

    with patch("app.tasks.notification_tasks.SessionLocal", return_value=mock_session):
        res = _deliver(mock_task, str(mock_notif.id), mock_send)

    assert res == {"status": "skipped"}
    assert mock_notif.attempt_count == 1  # Not incremented
    mock_send.assert_not_called()
    mock_task.retry.assert_not_called()
