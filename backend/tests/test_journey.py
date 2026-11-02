"""
End-to-end journey test covering the full notification service lifecycle.
"""
import contextlib
from datetime import datetime, timedelta, timezone
import re
from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.config import get_settings
from app.database import SessionLocal
from app.limiter import limiter
from app.main import app
from app.models.api_client import ApiClient
from app.models.notification import Notification
from app.models.provider_credential import ProviderCredential
from app.models.suppression import Suppression
from app.models.template import Template
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.rate_limit import get_redis_client
from app.services.tenancy import get_default_workspace
from app.tasks.notification_tasks import send_email_task, send_sms_task, send_webhook_task

client = TestClient(app)
settings = get_settings()


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


def _reset_db():
    try:
        r = get_redis_client()
        r.flushdb()
    except Exception:
        pass
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM delivery_events"))
        db.execute(text("DELETE FROM delivery_attempts"))
        db.execute(text("DELETE FROM notifications"))
        db.execute(text("DELETE FROM suppressions"))
        db.execute(text("DELETE FROM templates"))
        db.execute(text("DELETE FROM api_clients"))
        db.execute(text("DELETE FROM invitations"))
        db.execute(text("DELETE FROM memberships"))
        db.execute(text("DELETE FROM users"))
        db.execute(text("DELETE FROM provider_credentials"))
        db.execute(text("DELETE FROM workspaces WHERE slug != 'default'"))
        default_ws = db.execute(select(Workspace).where(Workspace.slug == "default")).scalar_one_or_none()
        if default_ws:
            default_ws.plan = "unlimited"
            default_ws.use_platform_providers = True
        db.commit()
    finally:
        db.close()


def test_complete_platform_journey():
    limiter.reset()
    _reset_db()

    captured_emails = []

    def mock_queue_system_email(to, subject, body):
        captured_emails.append({"to": to, "subject": subject, "body": body})

    mock_sent_emails = []

    def mock_send_email(recipient, subject, body, on_attempt=None, providers=None):
        msg_id = f"brevo-{uuid.uuid4().hex[:12]}"
        mock_sent_emails.append({"recipient": recipient, "subject": subject, "body": body, "id": msg_id})
        return msg_id

    def mock_send_webhook(url=None, text=None, *args, **kwargs):
        return f"wh-{uuid.uuid4().hex[:12]}"

    with patch("app.api.accounts.queue_system_email", side_effect=mock_queue_system_email), \
         patch("app.api.invitations.queue_system_email", side_effect=mock_queue_system_email), \
         patch("app.services.system_mail.queue_system_email", side_effect=mock_queue_system_email), \
         patch("app.tasks.notification_tasks.send_email", side_effect=mock_send_email), \
         patch("app.tasks.notification_tasks.send_webhook", side_effect=mock_send_webhook), \
         patch("app.api.providers._send_brevo", return_value="brevo-test-ok"), \
         patch.object(send_email_task, "apply_async") as mock_email_async, \
         patch.object(send_webhook_task, "apply_async") as mock_wh_async, \
         _settings_override(
             signup_mode="invite_only",
             require_email_verification=True,
             unsubscribe_secret="test-unsubscribe-secret-at-least-32-chars-long",
             public_base_url="http://localhost:8000",
             quota_enabled=True,
         ):

        # -------------------------------------------------------------------
        # 1. Fresh state; first signup in invite_only mode becomes superadmin
        # -------------------------------------------------------------------
        resp_su = client.post(
            "/auth/signup",
            json={"email": "superadmin@example.com", "password": "superpassword123!"},
        )
        assert resp_su.status_code == 201, resp_su.text
        data_su = resp_su.json()
        assert data_su["is_superadmin"] is True
        token_su = data_su["access_token"]
        h_su = {"Authorization": f"Bearer {token_su}"}

        # Verify default workspace is assigned to superadmin
        db = SessionLocal()
        default_ws = get_default_workspace(db)
        assert data_su["workspace"]["id"] == str(default_ws.id)
        assert default_ws.plan == "unlimited"
        db.close()

        # -------------------------------------------------------------------
        # 2. Switch to open mode; second person signs up, gets a new workspace;
        #    login refused until verification; link verifies and logs in.
        # -------------------------------------------------------------------
        with _settings_override(signup_mode="open"):
            resp_u2_signup = client.post(
                "/auth/signup",
                json={
                    "email": "owner2@example.com",
                    "password": "password123!",
                    "workspace_name": "Workspace Two",
                },
            )
            assert resp_u2_signup.status_code == 202
            assert len(captured_emails) >= 1

            # Login refused until verified
            resp_u2_fail = client.post(
                "/auth/login",
                json={"email": "owner2@example.com", "password": "password123!"},
            )
            assert resp_u2_fail.status_code == 403
            assert "Email not verified" in resp_u2_fail.text

            # Extract verification token and verify
            v_email = captured_emails[-1]
            assert "owner2@example.com" in v_email["to"]
            match = re.search(r"token=([A-Za-z0-9_\-\.]+)", v_email["body"])
            assert match is not None
            v_token = match.group(1)

            resp_verify = client.post("/auth/verify-email", json={"token": v_token})
            assert resp_verify.status_code == 200

            # Login succeeds
            resp_u2_login = client.post(
                "/auth/login",
                json={"email": "owner2@example.com", "password": "password123!"},
            )
            assert resp_u2_login.status_code == 200
            token_u2 = resp_u2_login.json()["access_token"]
            ws2_id = resp_u2_login.json()["workspace"]["id"]
            h2 = {"Authorization": f"Bearer {token_u2}"}

        # -------------------------------------------------------------------
        # 3. In that workspace: sending email before connecting a provider returns
        #    422 no_provider; PUT /providers/brevo & POST /providers/brevo/test succeed
        # -------------------------------------------------------------------
        resp_no_prov = client.post(
            "/notifications/email",
            headers=h2,
            json={"recipient": "dest@example.com", "subject": "S", "body": "B"},
        )
        assert resp_no_prov.status_code == 422
        assert resp_no_prov.json()["code"] == "no_provider"

        # Configure Brevo
        resp_put_brevo = client.put(
            "/providers/brevo",
            headers=h2,
            json={"api_key": "xkeysib-supersecretapi1234", "from_email": "sender@ws2.com", "from_name": "WS2"},
        )
        assert resp_put_brevo.status_code == 200
        assert "supersecretapi1234" not in resp_put_brevo.text
        assert resp_put_brevo.json()["hints"]["api_key"] == "1234"

        # Test Brevo connection
        resp_test_brevo = client.post(
            "/providers/brevo/test",
            headers=h2,
            json={"to": "test@example.com"},
        )
        assert resp_test_brevo.status_code == 200
        assert resp_test_brevo.json()["ok"] is True

        # -------------------------------------------------------------------
        # 4. Create template & API key; send template, scheduled, marketing,
        #    bulk send of 3 (1 suppressed) and Slack webhook; deliver and assert.
        # -------------------------------------------------------------------
        resp_tmpl = client.post(
            "/templates",
            headers=h2,
            json={
                "name": "welcome_tmpl",
                "channel": "email",
                "subject_template": "Hello {{ name }}",
                "body_template": "Welcome to our platform {{ name }}!",
            },
        )
        assert resp_tmpl.status_code == 201
        tmpl_id = resp_tmpl.json()["id"]

        resp_client = client.post("/admin/clients", headers=h2, json={"name": "prod_key"})
        assert resp_client.status_code == 201
        api_key = resp_client.json()["api_key"]
        h_api = {"X-API-Key": api_key}

        # Send template email
        resp_t_email = client.post(
            "/notifications/email",
            headers=h_api,
            json={"recipient": "alice@example.com", "template_id": tmpl_id, "variables": {"name": "Alice"}},
        )
        assert resp_t_email.status_code == 200
        id_t_email = resp_t_email.json()["id"]

        # Send scheduled email (not delivered immediately)
        future_iso = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        resp_sched = client.post(
            "/notifications/email",
            headers=h_api,
            json={"recipient": "future@example.com", "subject": "Future", "body": "Later", "scheduled_at": future_iso},
        )
        assert resp_sched.status_code == 200
        assert resp_sched.json()["status"] == "scheduled"

        # Add suppression for suppressed_user@example.com
        client.post(
            "/suppressions",
            headers=h2,
            json={"channel": "email", "recipient": "suppressed_user@example.com", "reason": "bounce"},
        )

        # Send marketing email (should receive unsubscribe footer at delivery)
        resp_mkt = client.post(
            "/notifications/email",
            headers=h_api,
            json={"recipient": "mkt@example.com", "subject": "Special Offer", "body": "Discount code inside", "category": "marketing"},
        )
        assert resp_mkt.status_code == 200
        id_mkt = resp_mkt.json()["id"]

        # Bulk send of 3 (one recipient is suppressed)
        resp_bulk = client.post(
            "/notifications/bulk",
            headers=h_api,
            json={
                "channel": "email",
                "subject": "Newsletter",
                "body": "Weekly update",
                "recipients": [
                    {"recipient": "bulk1@example.com"},
                    {"recipient": "bulk2@example.com"},
                    {"recipient": "suppressed_user@example.com"},
                ],
            },
        )
        assert resp_bulk.status_code == 200
        assert resp_bulk.json()["queued"] == 2
        assert resp_bulk.json()["suppressed"] == 1
        bulk_ids = resp_bulk.json()["ids"]

        # Send Slack webhook
        resp_wh = client.post(
            "/notifications/webhook",
            headers=h_api,
            json={"recipient": "https://hooks.slack.com/services/xxx", "body": "Deployment completed"},
        )
        assert resp_wh.status_code in (200, 201)
        id_wh = resp_wh.json()["id"]

        # Deliver queued messages synchronously
        send_email_task(id_t_email)
        send_email_task(id_mkt)
        send_email_task(bulk_ids[0])
        send_webhook_task(id_wh)

        # Assert marketing email received unsubscribe footer
        mkt_sent = [m for m in mock_sent_emails if m["recipient"] == "mkt@example.com"]
        assert len(mkt_sent) == 1
        assert "To unsubscribe:" in mkt_sent[0]["body"]

        # Assert timeline on template email
        resp_timeline = client.get(f"/notifications/{id_t_email}/timeline", headers=h_api)
        assert resp_timeline.status_code == 200
        data_tl = resp_timeline.json()
        assert len(data_tl) >= 1

        # -------------------------------------------------------------------
        # 5. Simulate per-workspace Brevo webhooks (delivered & hard bounce)
        # -------------------------------------------------------------------
        db = SessionLocal()
        ws2_obj = db.get(Workspace, uuid.UUID(ws2_id))
        wh_token = ws2_obj.webhook_token

        # Delivered webhook for id_t_email
        notif_delivered = db.get(Notification, uuid.UUID(id_t_email))
        p_msg_id_1 = notif_delivered.provider_message_id
        db.close()

        resp_wh_deliv = client.post(
            f"/webhooks/brevo/{wh_token}",
            json={"message-id": p_msg_id_1, "event": "delivered"},
        )
        assert resp_wh_deliv.status_code == 200

        db = SessionLocal()
        notif_delivered_refreshed = db.get(Notification, uuid.UUID(id_t_email))
        assert notif_delivered_refreshed.status == "delivered"

        # Hard bounce for bulk_ids[0]
        notif_bounce = db.get(Notification, uuid.UUID(bulk_ids[0]))
        p_msg_id_2 = notif_bounce.provider_message_id
        db.close()

        resp_wh_bounce = client.post(
            f"/webhooks/brevo/{wh_token}",
            json={"message-id": p_msg_id_2, "event": "hard_bounce"},
        )
        assert resp_wh_bounce.status_code == 200

        db = SessionLocal()
        notif_bounce_refreshed = db.get(Notification, uuid.UUID(bulk_ids[0]))
        assert notif_bounce_refreshed.status == "bounced"

        # Verify bounce suppression exists for recipient in ws2
        bounce_sup = db.scalar(
            select(Suppression).where(
                Suppression.workspace_id == uuid.UUID(ws2_id),
                Suppression.recipient == notif_bounce_refreshed.recipient,
            )
        )
        assert bounce_sup is not None
        assert bounce_sup.reason == "bounce"
        db.close()

        # -------------------------------------------------------------------
        # 6. Quota: lower plan limit, assert 429 body, verify GET /usage
        # -------------------------------------------------------------------
        # Ensure ws2 is on free plan
        client.patch(f"/admin/workspaces/{ws2_id}", headers=h_su, json={"plan": "free"})

        now = datetime.now(timezone.utc)
        key_d = f"quota:{ws2_id}:d:{now.strftime('%Y%m%d')}"
        r = get_redis_client()
        r.set(key_d, 100)  # Free plan daily limit is 100

        resp_quota_exceeded = client.post(
            "/notifications/email",
            headers=h2,
            json={"recipient": "quota_test@example.com", "subject": "S", "body": "B"},
        )
        assert resp_quota_exceeded.status_code == 429
        data_qe = resp_quota_exceeded.json()
        assert data_qe["code"] == "quota_exceeded"
        assert data_qe["limit"] == 100

        resp_usage = client.get("/usage", headers=h2)
        assert resp_usage.status_code == 200
        data_u = resp_usage.json()
        assert data_u["plan"] == "free"
        assert data_u["daily"]["used"] == 100
        assert data_u["daily"]["limit"] == 100

        r.delete(key_d)

        # -------------------------------------------------------------------
        # 7. Invite a teammate as viewer; accept through link; check permissions
        # -------------------------------------------------------------------
        resp_inv = client.post(
            "/workspaces/current/invitations",
            headers=h2,
            json={"email": "viewer@ws2.com", "role": "viewer"},
        )
        assert resp_inv.status_code == 201
        inv_email = captured_emails[-1]
        assert "viewer@ws2.com" in inv_email["to"]
        m_inv = re.search(r"token=([A-Za-z0-9_\-\.]+)", inv_email["body"])
        assert m_inv is not None
        inv_token = m_inv.group(1)

        # Accept invitation
        resp_acc = client.post(
            "/auth/accept-invitation",
            json={"token": inv_token, "password": "viewerpassword123!"},
        )
        assert resp_acc.status_code == 200
        token_viewer = resp_acc.json()["access_token"]
        h_viewer = {"Authorization": f"Bearer {token_viewer}"}

        # Viewer can read notifications
        resp_v_read = client.get("/notifications", headers=h_viewer)
        assert resp_v_read.status_code == 200
        assert len(resp_v_read.json()) >= 1

        # Viewer forbidden on write
        resp_v_write = client.post(
            "/notifications/email",
            headers=h_viewer,
            json={"recipient": "vw@example.com", "subject": "S", "body": "B"},
        )
        assert resp_v_write.status_code == 403

        # -------------------------------------------------------------------
        # 8. Isolation: a third workspace sees none of the above data
        # -------------------------------------------------------------------
        with _settings_override(signup_mode="open"):
            client.post(
                "/auth/signup",
                json={"email": "owner3@example.com", "password": "password123!", "workspace_name": "Workspace Three"},
            )
            token3 = re.search(r"token=([A-Za-z0-9_\-\.]+)", captured_emails[-1]["body"]).group(1)
            client.post("/auth/verify-email", json={"token": token3})
            resp_l3 = client.post("/auth/login", json={"email": "owner3@example.com", "password": "password123!"})
            token3_access = resp_l3.json()["access_token"]
            h3 = {"Authorization": f"Bearer {token3_access}"}

        # Workspace 3 sees empty collections
        assert client.get("/notifications", headers=h3).json() == []
        assert client.get("/templates", headers=h3).json() == []
        assert client.get("/admin/clients", headers=h3).json() == []
        assert client.get("/suppressions", headers=h3).json() == []

        # -------------------------------------------------------------------
        # 9. Password reset flow works once; the old token is rejected afterwards
        # -------------------------------------------------------------------
        resp_forgot = client.post("/auth/forgot-password", json={"email": "owner2@example.com"})
        assert resp_forgot.status_code == 202
        reset_email_obj = captured_emails[-1]
        assert "owner2@example.com" in reset_email_obj["to"]
        m_rst = re.search(r"token=([A-Za-z0-9_\-\.]+)", reset_email_obj["body"])
        assert m_rst is not None
        reset_token = m_rst.group(1)

        # Reset password
        resp_rst = client.post("/auth/reset-password", json={"token": reset_token, "new_password": "brandnewpassword123!"})
        assert resp_rst.status_code == 200

        # Old reset token rejected when reused
        resp_rst_reuse = client.post("/auth/reset-password", json={"token": reset_token, "new_password": "evennewerpass123!"})
        assert resp_rst_reuse.status_code == 400

        # Login with new password succeeds
        resp_new_login = client.post("/auth/login", json={"email": "owner2@example.com", "password": "brandnewpassword123!"})
        assert resp_new_login.status_code == 200
