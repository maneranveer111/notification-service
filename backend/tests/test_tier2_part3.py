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
from app.models.notification import Notification
from app.models.suppression import Suppression
from app.tasks.notification_tasks import send_email_task, send_sms_task, send_webhook_task
from app.services.unsubscribe import make_token, verify_token
from app.services.webhook_service import send_webhook
from app.services.errors import PermanentError, TransientError

client = TestClient(app)
settings = get_settings()
ADMIN_HEADERS = {"X-API-Key": settings.api_key}


@pytest.fixture(autouse=True)
def mock_tasks():
    limiter.reset()
    with patch.object(send_email_task, "apply_async", return_value=MagicMock()) as m_email, \
         patch.object(send_sms_task, "apply_async", return_value=MagicMock()) as m_sms, \
         patch.object(send_webhook_task, "apply_async", return_value=MagicMock()) as m_webhook:
        yield m_email, m_sms, m_webhook
    limiter.reset()


def _ensure_unsubscribe_secret():
    # Ensure settings has an unsubscribe secret for tests
    return patch.object(settings, "unsubscribe_secret", "test_unsub_secret_123")


def test_marketing_to_opted_out_recipient_suppressed(mock_tasks):
    m_email, _, _ = mock_tasks
    db = next(get_db())
    recipient = f"optout_{uuid.uuid4().hex[:8]}@example.com"

    # Add suppression opt_out
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "opt_out"},
    )

    with _ensure_unsubscribe_secret():
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": recipient,
                "subject": "Promo",
                "body": "Buy now",
                "category": "marketing",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "suppressed"
    m_email.assert_not_called()

    # Check notification in DB has error_message
    notif = db.get(Notification, uuid.UUID(data["id"]))
    assert notif is not None
    assert notif.status == "suppressed"
    assert "Recipient suppressed (opt_out)" in notif.error_message


def test_transactional_to_opted_out_recipient_enqueued(mock_tasks):
    m_email, _, _ = mock_tasks
    recipient = f"optout_tx_{uuid.uuid4().hex[:8]}@example.com"

    # Add suppression opt_out
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "opt_out"},
    )

    with _ensure_unsubscribe_secret():
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": recipient,
                "subject": "Receipt",
                "body": "Your invoice",
                "category": "transactional",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    m_email.assert_called_once()


def test_transactional_to_bounced_recipient_suppressed(mock_tasks):
    m_email, _, _ = mock_tasks
    recipient = f"bounced_{uuid.uuid4().hex[:8]}@example.com"

    # Add suppression bounce
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "bounce"},
    )

    with _ensure_unsubscribe_secret():
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": recipient,
                "subject": "Receipt",
                "body": "Your invoice",
                "category": "transactional",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "suppressed"
    m_email.assert_not_called()


def test_brevo_hard_bounce_creates_suppression_and_soft_bounce_does_not():
    db = next(get_db())
    hard_recip = f"hb_{uuid.uuid4().hex[:8]}@example.com"
    soft_recip = f"sb_{uuid.uuid4().hex[:8]}@example.com"

    msg_id_hb = f"msg_{uuid.uuid4().hex}"
    msg_id_sb = f"msg_{uuid.uuid4().hex}"

    notif_hb = Notification(
        channel="email",
        recipient=hard_recip,
        subject="Test HB",
        body="Body",
        status="sent",
        provider="brevo",
        provider_message_id=msg_id_hb,
    )
    notif_sb = Notification(
        channel="email",
        recipient=soft_recip,
        subject="Test SB",
        body="Body",
        status="sent",
        provider="brevo",
        provider_message_id=msg_id_sb,
    )
    db.add(notif_hb)
    db.add(notif_sb)
    db.commit()

    with patch.object(settings, "webhook_verify", False):
        # 1. Hard bounce webhook
        resp_hb = client.post(
            "/webhooks/brevo",
            json={"event": "hard_bounce", "message-id": msg_id_hb},
        )
        assert resp_hb.status_code == 200

        # 2. Soft bounce webhook
        resp_sb = client.post(
            "/webhooks/brevo",
            json={"event": "soft_bounce", "message-id": msg_id_sb},
        )
        assert resp_sb.status_code == 200

    # Verify hard_recip is in suppressions with reason='bounce'
    stmt_hb = select(Suppression).where(Suppression.recipient == hard_recip.lower())
    sup_hb = db.execute(stmt_hb).scalar_one_or_none()
    assert sup_hb is not None
    assert sup_hb.reason == "bounce"
    assert sup_hb.source == "bounce"

    # Verify soft_recip is NOT in suppressions
    stmt_sb = select(Suppression).where(Suppression.recipient == soft_recip.lower())
    sup_sb = db.execute(stmt_sb).scalar_one_or_none()
    assert sup_sb is None


def test_unsubscribe_token_roundtrip_and_post_suppression():
    db = next(get_db())
    recipient = f"unsub_{uuid.uuid4().hex[:8]}@example.com"

    with _ensure_unsubscribe_secret():
        token = make_token("email", recipient)
        parsed = verify_token(token)
        assert parsed == ("email", recipient.lower())

        # GET confirm page does NOT unsubscribe
        resp_get = client.get(f"/unsubscribe?token={token}")
        assert resp_get.status_code == 200
        assert "Confirm Unsubscribe" in resp_get.text

        stmt = select(Suppression).where(Suppression.recipient == recipient.lower())
        assert db.execute(stmt).scalar_one_or_none() is None

        # POST unsubscribes
        resp_post = client.post(
            "/unsubscribe",
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp_post.status_code == 200
        assert "You have been unsubscribed" in resp_post.text

        sup = db.execute(stmt).scalar_one_or_none()
        assert sup is not None
        assert sup.reason == "opt_out"
        assert sup.source == "unsubscribe_link"


def test_tampered_token_returns_400():
    with _ensure_unsubscribe_secret():
        token = make_token("email", "legit@example.com")
        tampered = token[:-4] + "xxxx"
        resp = client.get(f"/unsubscribe?token={tampered}")
        assert resp.status_code == 400

        resp_post = client.post(
            "/unsubscribe",
            data={"token": tampered},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp_post.status_code == 400


def test_marketing_without_unsubscribe_secret_returns_422():
    with patch.object(settings, "unsubscribe_secret", None):
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": "marketing_fail@example.com",
                "subject": "Promo",
                "body": "Buy now",
                "category": "marketing",
            },
        )
    assert resp.status_code == 422
    assert "unsubscribe_secret" in resp.json()["detail"].lower()


def test_footer_appended_at_send_time_and_stored_body_unchanged():
    db = next(get_db())
    recipient = f"footer_{uuid.uuid4().hex[:8]}@example.com"
    original_body = "Hello valued user"

    with _ensure_unsubscribe_secret():
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": recipient,
                "subject": "Marketing Newsletter",
                "body": original_body,
                "category": "marketing",
            },
        )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]

    # Verify stored body in DB is untouched
    notif = db.get(Notification, uuid.UUID(notif_id))
    assert notif.body == original_body

    # Now verify delivery appends footer
    from app.tasks.notification_tasks import _deliver
    sent_bodies = []

    def mock_send(n):
        return ("brevo", "brevo-id-123")

    # Call _deliver and inspect via mocking send_email inside notification_tasks
    with _ensure_unsubscribe_secret(), \
         patch("app.tasks.notification_tasks.send_email", side_effect=lambda recipient, subject, body: ("brevo-id", None)) as m_send:
        task_mock = MagicMock()
        _deliver(task_mock, str(notif_id), lambda n: ("brevo", "msg-123"))
        db.refresh(notif)
        # Check send_email was called with the footer attached
        assert m_send.called
        call_kwargs = m_send.call_args[1] if m_send.call_args[1] else {}
        call_args = m_send.call_args[0] if m_send.call_args[0] else ()
        body_sent = call_kwargs.get("body") or (call_args[2] if len(call_args) > 2 else "")
        assert "/unsubscribe?token=" in body_sent
        assert original_body in body_sent
        # The stored body remains unchanged
        assert notif.body == original_body


def test_webhook_disallowed_host_returns_422():
    resp = client.post(
        "/notifications/webhook",
        headers=ADMIN_HEADERS,
        json={
            "recipient": "https://evil.internal/api/webhook",
            "body": "Alert text",
        },
    )
    assert resp.status_code == 422
    assert "not in the allowed hosts" in resp.json()["detail"].lower()


def test_webhook_allowed_host_enqueued(mock_tasks):
    _, _, m_webhook = mock_tasks
    webhook_url = "https://hooks.slack.com/services/T00/B00/XXXX123456"
    resp = client.post(
        "/notifications/webhook",
        headers=ADMIN_HEADERS,
        json={
            "recipient": webhook_url,
            "body": "Deployment succeeded",
            "priority": "high",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["channel"] == "webhook"
    m_webhook.assert_called_once()
    _, kwargs = m_webhook.call_args
    assert kwargs.get("queue") == f"{settings.celery_queue}_high"


def test_webhook_adapter_classification():
    mock_429 = MagicMock(status_code=429, is_redirect=False)
    with patch("requests.post", return_value=mock_429):
        with pytest.raises(TransientError):
            send_webhook("https://hooks.slack.com/services/T00", "test")

    mock_502 = MagicMock(status_code=502, is_redirect=False)
    with patch("requests.post", return_value=mock_502):
        with pytest.raises(TransientError):
            send_webhook("https://hooks.slack.com/services/T00", "test")

    mock_400 = MagicMock(status_code=400, is_redirect=False)
    with patch("requests.post", return_value=mock_400):
        with pytest.raises(PermanentError):
            send_webhook("https://hooks.slack.com/services/T00", "test")

    mock_302 = MagicMock(status_code=302, is_redirect=True)
    with patch("requests.post", return_value=mock_302):
        with pytest.raises(PermanentError):
            send_webhook("https://hooks.slack.com/services/T00", "test")


def test_webhook_url_masked_in_responses():
    webhook_url = "https://discord.com/api/webhooks/1234567890/SECRET_TOKEN_XYZ123"
    resp = client.post(
        "/notifications/webhook",
        headers=ADMIN_HEADERS,
        json={
            "recipient": webhook_url,
            "body": "Notice",
        },
    )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]

    get_resp = client.get(f"/notifications/{notif_id}", headers=ADMIN_HEADERS)
    assert get_resp.status_code == 200
    recipient = get_resp.json()["recipient"]
    assert "SECRET_TOKEN" not in recipient
    assert recipient == "https://discord.com/...XYZ123"


# ---------------------------------------------------------------------------
# Security Regression Tests
# ---------------------------------------------------------------------------
def test_make_and_verify_token_reject_missing_or_empty_secret():
    """Vulnerability 1: Ensure tokens cannot be created or verified with missing or empty secret."""
    for empty_val in [None, ""]:
        with patch.object(settings, "unsubscribe_secret", empty_val):
            # 1. make_token must reject
            with pytest.raises(ValueError, match="missing or empty"):
                make_token("email", "user@example.com")

            # 2. verify_token must return None even for token signed with empty key
            fake_payload = "email|user@example.com"
            import base64, hmac as _hmac, hashlib
            b64_payload = base64.urlsafe_b64encode(fake_payload.encode()).rstrip(b"=").decode()
            fake_sig = base64.urlsafe_b64encode(_hmac.new(b"", b64_payload.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
            forged_token = f"{b64_payload}.{fake_sig}"

            assert verify_token(forged_token) is None
            assert verify_token("invalid.token") is None

            # 3. Public unsubscribe endpoints must return 400
            resp_get = client.get(f"/unsubscribe?token={forged_token}")
            assert resp_get.status_code == 400

            resp_post = client.post(
                "/unsubscribe",
                data={"token": forged_token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert resp_post.status_code == 400


def test_webhook_exceptions_do_not_leak_secret_url():
    """Vulnerability 2: Timeout and ConnectionError must never expose the complete URL/path/secret."""
    import requests
    secret_token = "SECRET_TOKEN_VALUE_98765"
    secret_url = f"https://hooks.slack.com/services/T123/B456/{secret_token}"

    # 1. Timeout exception
    with patch("requests.post", side_effect=requests.exceptions.ConnectTimeout(f"Failed to connect to {secret_url}")):
        with pytest.raises(TransientError) as exc_info:
            send_webhook(secret_url, "test payload")
        err_msg = str(exc_info.value)
        assert secret_token not in err_msg
        assert "/services/T123/B456/" not in err_msg
        assert "ConnectTimeout" in err_msg
        assert "hooks.slack.com" in err_msg

    # 2. ConnectionError exception
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError(f"Connection refused at {secret_url}")):
        with pytest.raises(TransientError) as exc_info:
            send_webhook(secret_url, "test payload")
        err_msg = str(exc_info.value)
        assert secret_token not in err_msg
        assert "/services/T123/B456/" not in err_msg
        assert "ConnectionError" in err_msg
        assert "hooks.slack.com" in err_msg


def test_webhook_error_message_sanitized_in_db():
    """Vulnerability 2: notification.error_message must never store unmasked webhook secrets."""
    db = next(get_db())
    secret_token = "DISCORD_VERY_SECRET_KEY_123"
    webhook_url = f"https://discord.com/api/webhooks/99999/{secret_token}"

    notif = Notification(
        channel="webhook",
        recipient=webhook_url,
        body="Alert",
        status="pending",
        provider="discord",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    from app.tasks.notification_tasks import _deliver
    task_mock = MagicMock()

    # Simulate a failure that leaks raw URL in the message
    raw_leak_msg = f"Failed to post to {webhook_url}: 400 Bad Request"
    _deliver(task_mock, str(notif.id), MagicMock(side_effect=PermanentError(raw_leak_msg, failover=False)))

    db.refresh(notif)
    assert notif.status == "failed"
    assert secret_token not in notif.error_message
    assert "/api/webhooks/99999/" not in notif.error_message
    assert "https://discord.com/" in notif.error_message


# ---------------------------------------------------------------------------
# Suppression Escalation and Scheduled Delivery Suppression Regression Tests
# ---------------------------------------------------------------------------
def test_hard_bounce_escalates_opt_out_to_bounce():
    db = next(get_db())
    recipient = f"escalate_{uuid.uuid4().hex[:8]}@example.com"
    msg_id = f"msg_{uuid.uuid4().hex}"

    # 1. Pre-existing opt_out suppression
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "opt_out"},
    )
    stmt = select(Suppression).where(Suppression.recipient == recipient.lower())
    sup = db.execute(stmt).scalar_one()
    assert sup.reason == "opt_out"

    # 2. Sent notification with this message ID
    notif = Notification(
        channel="email",
        recipient=recipient,
        subject="Test Escalation",
        body="Body",
        status="sent",
        provider="brevo",
        provider_message_id=msg_id,
    )
    db.add(notif)
    db.commit()

    # 3. Hard bounce webhook arrives
    with patch.object(settings, "webhook_verify", False):
        resp = client.post(
            "/webhooks/brevo",
            json={"event": "hard_bounce", "message-id": msg_id},
        )
        assert resp.status_code == 200

    # 4. Verify escalation to bounce
    db.expire_all()
    sup_updated = db.execute(stmt).scalar_one()
    assert sup_updated.reason == "bounce"
    assert sup_updated.source == "bounce"


def test_transactional_delivery_blocked_after_bounce(mock_tasks):
    m_email, _, _ = mock_tasks
    db = next(get_db())
    recipient = f"tx_blocked_{uuid.uuid4().hex[:8]}@example.com"

    # Direct bounce suppression
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "bounce"},
    )

    with _ensure_unsubscribe_secret():
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": recipient,
                "subject": "Critical Security Alert",
                "body": "Your password was reset",
                "category": "transactional",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "suppressed"
    m_email.assert_not_called()

    notif = db.get(Notification, uuid.UUID(data["id"]))
    assert notif.status == "suppressed"
    assert "Recipient suppressed (bounce)" in notif.error_message


def test_scheduled_marketing_notification_blocked_after_unsubscribe():
    from app.tasks.notification_tasks import _deliver
    db = next(get_db())
    recipient = f"sched_unsub_{uuid.uuid4().hex[:8]}@example.com"
    future_time = datetime.now(timezone.utc) + timedelta(days=2)

    # 1. Schedule marketing notification when recipient is NOT suppressed
    with _ensure_unsubscribe_secret():
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": recipient,
                "subject": "Future Sale",
                "body": "Don't miss out",
                "scheduled_at": future_time.isoformat(),
                "category": "marketing",
            },
        )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]
    assert resp.json()["status"] == "scheduled"

    # 2. Recipient unsubscribes before scheduled delivery
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "opt_out"},
    )

    # 3. Deliver scheduled notification
    mock_send = MagicMock()
    task_mock = MagicMock()
    res = _deliver(task_mock, notif_id, mock_send)

    assert res["status"] == "suppressed"
    mock_send.assert_not_called()

    notif = db.get(Notification, uuid.UUID(notif_id))
    db.refresh(notif)
    assert notif.status == "suppressed"
    assert "Recipient suppressed (opt_out)" in notif.error_message


def test_scheduled_transactional_notification_still_allowed_after_opt_out():
    from app.tasks.notification_tasks import _deliver
    db = next(get_db())
    recipient = f"sched_tx_{uuid.uuid4().hex[:8]}@example.com"
    future_time = datetime.now(timezone.utc) + timedelta(days=1)

    # Recipient has opt_out
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "opt_out"},
    )

    # Schedule transactional notification
    with _ensure_unsubscribe_secret():
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": recipient,
                "subject": "Monthly Statement",
                "body": "Here is your statement",
                "scheduled_at": future_time.isoformat(),
                "category": "transactional",
            },
        )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]
    assert resp.json()["status"] == "scheduled"

    # Deliver scheduled notification
    mock_send = MagicMock(return_value=("brevo", "msg-statement-123"))
    task_mock = MagicMock()
    res = _deliver(task_mock, notif_id, mock_send)

    assert res["status"] == "sent"
    mock_send.assert_called_once()

    notif = db.get(Notification, uuid.UUID(notif_id))
    db.refresh(notif)
    assert notif.status == "sent"


def test_scheduled_notification_blocked_after_bounce():
    from app.tasks.notification_tasks import _deliver
    db = next(get_db())
    recipient = f"sched_bounce_{uuid.uuid4().hex[:8]}@example.com"
    future_time = datetime.now(timezone.utc) + timedelta(days=1)

    # Schedule notification when recipient is active
    with _ensure_unsubscribe_secret():
        resp = client.post(
            "/notifications/email",
            headers=ADMIN_HEADERS,
            json={
                "recipient": recipient,
                "subject": "Account Notice",
                "body": "Important update",
                "scheduled_at": future_time.isoformat(),
                "category": "transactional",
            },
        )
    assert resp.status_code == 200
    notif_id = resp.json()["id"]

    # Address hard-bounced subsequently
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "bounce"},
    )

    # Deliver scheduled notification
    mock_send = MagicMock()
    task_mock = MagicMock()
    res = _deliver(task_mock, notif_id, mock_send)

    assert res["status"] == "suppressed"
    mock_send.assert_not_called()

    notif = db.get(Notification, uuid.UUID(notif_id))
    db.refresh(notif)
    assert notif.status == "suppressed"
    assert "Recipient suppressed (bounce)" in notif.error_message


# ---------------------------------------------------------------------------
# Area 1: Unsubscribe HTML Safety and Injection Prevention
# ---------------------------------------------------------------------------
def test_unsubscribe_html_escaping():
    malicious_email = 'hacker<script>alert("xss")</script>@example.com'
    with _ensure_unsubscribe_secret():
        token = make_token("email", malicious_email)

        # 1. GET confirmation page escapes script tags
        resp_get = client.get(f"/unsubscribe?token={token}")
        assert resp_get.status_code == 200
        assert "<script>alert" not in resp_get.text
        assert "&lt;script&gt;alert" in resp_get.text

        # 2. POST confirmation page escapes script tags
        resp_post = client.post(
            "/unsubscribe",
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp_post.status_code == 200
        assert "<script>alert" not in resp_post.text
        assert "&lt;script&gt;alert" in resp_post.text


# ---------------------------------------------------------------------------
# Area 2: Hard-Bounce Suppression Without Notification Lookup
# ---------------------------------------------------------------------------
def test_brevo_hard_bounce_suppresses_by_email_when_notification_unmatched():
    db = next(get_db())
    unmatched_email = f"unmatched_{uuid.uuid4().hex[:8]}@example.com"

    with patch.object(settings, "webhook_verify", False):
        resp = client.post(
            "/webhooks/brevo",
            json={
                "event": "hard_bounce",
                "message-id": "nonexistent-message-id-99999",
                "email": unmatched_email,
            },
        )
        assert resp.status_code == 200

    stmt = select(Suppression).where(Suppression.recipient == unmatched_email.lower())
    sup = db.execute(stmt).scalar_one_or_none()
    assert sup is not None
    assert sup.reason == "bounce"
    assert sup.source == "bounce"


def test_brevo_hard_bounce_rejects_malformed_email_when_notification_unmatched():
    db = next(get_db())
    bad_email = "malformed-email-not-valid"

    with patch.object(settings, "webhook_verify", False):
        resp = client.post(
            "/webhooks/brevo",
            json={
                "event": "hard_bounce",
                "message-id": "nonexistent-message-id-88888",
                "email": bad_email,
            },
        )
        assert resp.status_code == 200

    stmt = select(Suppression).where(Suppression.recipient == bad_email)
    sup = db.execute(stmt).scalar_one_or_none()
    assert sup is None


# ---------------------------------------------------------------------------
# Area 4 & 8: Webhook Provider Naming Consistency
# ---------------------------------------------------------------------------
def test_webhook_provider_name_consistent_before_and_after_delivery():
    db = next(get_db())

    # Slack webhook URL
    slack_url = "https://hooks.slack.com/services/T00/B00/test"
    resp_slack = client.post(
        "/notifications/webhook",
        headers=ADMIN_HEADERS,
        json={"recipient": slack_url, "body": "Slack notice"},
    )
    assert resp_slack.status_code == 200
    slack_id = resp_slack.json()["id"]

    notif_slack = db.get(Notification, uuid.UUID(slack_id))
    assert notif_slack.provider == "slack"

    # Discord webhook URL
    discord_url = "https://discord.com/api/webhooks/123/test"
    resp_discord = client.post(
        "/notifications/webhook",
        headers=ADMIN_HEADERS,
        json={"recipient": discord_url, "body": "Discord notice"},
    )
    assert resp_discord.status_code == 200
    discord_id = resp_discord.json()["id"]

    notif_discord = db.get(Notification, uuid.UUID(discord_id))
    assert notif_discord.provider == "discord"


# ---------------------------------------------------------------------------
# Area 5: Idempotency Handling on Suppressed Notifications
# ---------------------------------------------------------------------------
def test_idempotent_replay_on_suppressed_notification():
    recipient = f"idemp_sup_{uuid.uuid4().hex[:8]}@example.com"
    idemp_key = f"key-sup-{uuid.uuid4().hex}"

    # Pre-suppress
    client.post(
        "/suppressions",
        headers=ADMIN_HEADERS,
        json={"channel": "email", "recipient": recipient, "reason": "opt_out"},
    )

    payload = {
        "recipient": recipient,
        "subject": "Promo",
        "body": "Special Offer",
        "category": "marketing",
    }

    with _ensure_unsubscribe_secret():
        # First request
        res1 = client.post("/notifications/email", json=payload, headers={"Idempotency-Key": idemp_key, **ADMIN_HEADERS})
        assert res1.status_code == 200
        assert res1.json()["status"] == "suppressed"
        assert "Idempotent-Replay" not in res1.headers
        first_id = res1.json()["id"]

        # Exact replay
        res2 = client.post("/notifications/email", json=payload, headers={"Idempotency-Key": idemp_key, **ADMIN_HEADERS})
        assert res2.status_code == 200
        assert res2.json()["status"] == "suppressed"
        assert res2.headers.get("Idempotent-Replay") == "true"
        assert res2.json()["id"] == first_id

        # Conflict with different payload
        conflict_payload = dict(payload, subject="Different Subject")
        res3 = client.post("/notifications/email", json=conflict_payload, headers={"Idempotency-Key": idemp_key, **ADMIN_HEADERS})
        assert res3.status_code == 422
        assert "reused with a different request" in res3.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Area 6: Complete Bulk Suppression Matrix
# ---------------------------------------------------------------------------
def test_bulk_complete_suppression_matrix(mock_tasks):
    m_email, _, _ = mock_tasks
    db = next(get_db())

    recip_active = f"bulk_act_{uuid.uuid4().hex[:6]}@example.com"
    recip_optout = f"bulk_opt_{uuid.uuid4().hex[:6]}@example.com"
    recip_bounce = f"bulk_bnc_{uuid.uuid4().hex[:6]}@example.com"

    # Setup suppressions
    client.post("/suppressions", headers=ADMIN_HEADERS, json={"channel": "email", "recipient": recip_optout, "reason": "opt_out"})
    client.post("/suppressions", headers=ADMIN_HEADERS, json={"channel": "email", "recipient": recip_bounce, "reason": "bounce"})

    # 1. Marketing bulk: opt_out and bounce are suppressed; active is queued; duplicates deduplicated
    recipients_marketing = [
        {"recipient": recip_active},
        {"recipient": recip_optout},
        {"recipient": recip_bounce},
        {"recipient": recip_active.upper()},  # duplicate of active
    ]

    with _ensure_unsubscribe_secret():
        resp_m = client.post(
            "/notifications/bulk",
            headers=ADMIN_HEADERS,
            json={
                "channel": "email",
                "recipients": recipients_marketing,
                "subject": "Bulk Promo",
                "body": "Buy stuff",
                "category": "marketing",
            },
        )
    assert resp_m.status_code == 200
    data_m = resp_m.json()
    assert data_m["queued"] == 1
    assert data_m["suppressed"] == 2
    assert len(data_m["ids"]) == 3  # active, optout, bounce

    # 2. Transactional bulk: opt_out is NOT suppressed; bounce is suppressed; active is queued
    recip_active2 = f"bulk_act2_{uuid.uuid4().hex[:6]}@example.com"
    recipients_tx = [
        {"recipient": recip_active2},
        {"recipient": recip_optout},  # allowed for transactional
        {"recipient": recip_bounce},  # suppressed for transactional
    ]

    with _ensure_unsubscribe_secret():
        resp_tx = client.post(
            "/notifications/bulk",
            headers=ADMIN_HEADERS,
            json={
                "channel": "email",
                "recipients": recipients_tx,
                "subject": "Bulk Invoices",
                "body": "Invoice content",
                "category": "transactional",
            },
        )
    assert resp_tx.status_code == 200
    data_tx = resp_tx.json()
    assert data_tx["queued"] == 2
    assert data_tx["suppressed"] == 1
    assert len(data_tx["ids"]) == 3


# ---------------------------------------------------------------------------
# Area 7: Suppression CRUD and Authorization
# ---------------------------------------------------------------------------
def test_suppressions_crud_and_authorization():
    db = next(get_db())

    # Create non-admin client
    client_name = f"client_supp_{uuid.uuid4().hex[:8]}"
    resp_c = client.post(
        "/admin/clients",
        headers=ADMIN_HEADERS,
        json={"name": client_name, "rate_limit_per_minute": 60},
    )
    client_key = resp_c.json()["api_key"]
    client_headers = {"X-API-Key": client_key}

    # 1. Non-admin can create suppression (authenticated)
    recip = f"crud_{uuid.uuid4().hex[:8]}@example.com"
    resp_create = client.post(
        "/suppressions",
        headers=client_headers,
        json={"channel": "email", "recipient": recip, "reason": "opt_out"},
    )
    assert resp_create.status_code == 200
    sup_id = resp_create.json()["id"]

    # 2. Duplicate create is idempotent
    resp_dup = client.post(
        "/suppressions",
        headers=client_headers,
        json={"channel": "email", "recipient": recip, "reason": "opt_out"},
    )
    assert resp_dup.status_code == 200
    assert resp_dup.json()["id"] == sup_id

    # 3. Create with bounce escalates opt_out to bounce
    resp_esc = client.post(
        "/suppressions",
        headers=client_headers,
        json={"channel": "email", "recipient": recip, "reason": "bounce"},
    )
    assert resp_esc.status_code == 200
    assert resp_esc.json()["reason"] == "bounce"

    # 4. Non-admin cannot list suppressions
    resp_list_client = client.get("/suppressions", headers=client_headers)
    assert resp_list_client.status_code == 403

    # 5. Non-admin cannot delete suppression
    resp_del_client = client.delete(f"/suppressions/{sup_id}", headers=client_headers)
    assert resp_del_client.status_code == 403

    # 6. Admin can list suppressions
    resp_list_admin = client.get("/suppressions", headers=ADMIN_HEADERS)
    assert resp_list_admin.status_code == 200
    assert any(s["id"] == sup_id for s in resp_list_admin.json())

    # 7. Admin can delete suppression
    resp_del_admin = client.delete(f"/suppressions/{sup_id}", headers=ADMIN_HEADERS)
    assert resp_del_admin.status_code == 204

    # 8. Deleting nonexistent returns 404
    resp_del_404 = client.delete(f"/suppressions/{sup_id}", headers=ADMIN_HEADERS)
    assert resp_del_404.status_code == 404
