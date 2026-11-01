import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.database import get_db
from app.models.notification import Notification

client = TestClient(app)


def test_template_deletion_sets_notification_template_id_null():
    settings = get_settings()
    headers = {"X-API-Key": settings.api_key}

    # 1. Create a template
    tpl_resp = client.post(
        "/templates",
        headers=headers,
        json={
            "name": f"FK Test Template {uuid.uuid4().hex[:6]}",
            "channel": "email",
            "subject_template": "Welcome {{name}}!",
            "body_template": "Your verification code is {{code}}.",
        },
    )
    assert tpl_resp.status_code == 201, tpl_resp.text
    tpl_id = tpl_resp.json()["id"]

    # 2. Create a notification using the template (mock enqueue)
    with patch("app.api.notifications.enqueue_notification", return_value=None):
        notif_resp = client.post(
            "/notifications/email",
            headers=headers,
            json={
                "recipient": "fk_test@example.com",
                "template_id": tpl_id,
                "variables": {"name": "Bob", "code": "987654"},
            },
        )
    assert notif_resp.status_code in (200, 201), notif_resp.text
    notif_id = notif_resp.json()["id"]

    # 3. Delete the template
    del_resp = client.delete(f"/templates/{tpl_id}", headers=headers)
    assert del_resp.status_code == 204

    # 4. Assert template is deleted
    get_tpl = client.get(f"/templates/{tpl_id}", headers=headers)
    assert get_tpl.status_code == 404

    # 5. Assert notification still exists with template_id NULL and unchanged subject/body
    db = next(get_db())
    notif = db.get(Notification, uuid.UUID(notif_id))
    assert notif is not None
    assert notif.template_id is None
    assert notif.subject == "Welcome Bob!"
    assert notif.body == "Your verification code is 987654."
