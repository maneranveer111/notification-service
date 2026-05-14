from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Our valid API key (same as in .env)
API_KEY = "notifications-services-secret-key-2026"
HEADERS = {"X-API-Key": API_KEY}


class TestEmailNotification:
    """
    Tests for POST /notifications/email endpoint.
    """

    def test_queue_email_success(self):
        """
        Test that a valid email request:
        - Returns 200
        - Returns correct JSON structure
        - Status is 'pending'
        - Channel is 'email'
        """
        # Mock send_email_task.delay so Celery is not actually called
        with patch("app.api.notifications.send_email_task") as mock_task:
            mock_task.delay = MagicMock(return_value=None)

            response = client.post(
                "/notifications/email",
                headers=HEADERS,
                json={
                    "recipient": "test@example.com",
                    "subject": "Test Subject",
                    "body": "Test body content"
                }
            )

        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "pending"
        assert data["channel"] == "email"
        assert "id" in data

    def test_queue_email_invalid_email(self):
        """
        Test that invalid email format returns 422.
        """
        response = client.post(
            "/notifications/email",
            headers=HEADERS,
            json={
                "recipient": "not-an-email",
                "subject": "Test",
                "body": "Test body"
            }
        )

        assert response.status_code == 422

    def test_queue_email_missing_subject(self):
        """
        Test that missing subject returns 422.
        """
        response = client.post(
            "/notifications/email",
            headers=HEADERS,
            json={
                "recipient": "test@example.com",
                "body": "Test body"
            }
        )

        assert response.status_code == 422

    def test_queue_email_missing_body(self):
        """
        Test that missing body returns 422.
        """
        response = client.post(
            "/notifications/email",
            headers=HEADERS,
            json={
                "recipient": "test@example.com",
                "subject": "Test Subject"
            }
        )

        assert response.status_code == 422


class TestSMSNotification:
    """
    Tests for POST /notifications/sms endpoint.
    """

    def test_queue_sms_success(self):
        """
        Test that a valid SMS request:
        - Returns 200
        - Returns correct JSON structure
        - Status is 'pending'
        - Channel is 'sms'
        """
        with patch("app.api.notifications.send_sms_task") as mock_task:
            mock_task.delay = MagicMock(return_value=None)

            response = client.post(
                "/notifications/sms",
                headers=HEADERS,
                json={
                    "recipient": "+919673631519",
                    "message": "Test SMS message"
                }
            )

        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "pending"
        assert data["channel"] == "sms"
        assert "id" in data

    def test_queue_sms_missing_message(self):
        """
        Test that missing message returns 422.
        """
        response = client.post(
            "/notifications/sms",
            headers=HEADERS,
            json={
                "recipient": "+919673631519"
            }
        )

        assert response.status_code == 422


class TestGetNotification:
    """
    Tests for GET /notifications/{id} endpoint.
    """

    def test_get_notification_not_found(self):
        """
        Test that requesting non-existent notification returns 404.
        """
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(
            f"/notifications/{fake_id}",
            headers=HEADERS
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Notification not found"

    def test_get_notification_invalid_uuid(self):
        """
        Test that invalid UUID format returns 422.
        """
        response = client.get(
            "/notifications/not-a-valid-uuid",
            headers=HEADERS
        )

        assert response.status_code == 422

    def test_get_notification_success(self):
        """
        Test that we can create a notification and fetch it by ID.
        """
        # Step 1: Create notification
        with patch("app.api.notifications.send_email_task") as mock_task:
            mock_task.delay = MagicMock(return_value=None)

            create_response = client.post(
                "/notifications/email",
                headers=HEADERS,
                json={
                    "recipient": "test@example.com",
                    "subject": "Test",
                    "body": "Test body"
                }
            )

        notification_id = create_response.json()["id"]

        # Step 2: Fetch by ID
        get_response = client.get(
            f"/notifications/{notification_id}",
            headers=HEADERS
        )

        assert get_response.status_code == 200

        data = get_response.json()
        assert data["id"] == notification_id
        assert data["channel"] == "email"
        assert data["recipient"] == "test@example.com"


class TestListNotifications:
    """
    Tests for GET /notifications endpoint.
    """

    def test_list_notifications_success(self):
        """
        Test that listing notifications returns a list.
        """
        response = client.get(
            "/notifications",
            headers=HEADERS
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_notifications_filter_by_channel(self):
        """
        Test filtering by channel.
        """
        response = client.get(
            "/notifications?channel=email",
            headers=HEADERS
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Every item must be email channel
        for item in data:
            assert item["channel"] == "email"

    def test_list_notifications_filter_by_status(self):
        """
        Test filtering by status.
        """
        response = client.get(
            "/notifications?status=sent",
            headers=HEADERS
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Every item must have sent status
        for item in data:
            assert item["status"] == "sent"

    def test_list_notifications_pagination(self):
        """
        Test that limit and offset work correctly.
        """
        response = client.get(
            "/notifications?limit=2&offset=0",
            headers=HEADERS
        )

        assert response.status_code == 200
        data = response.json()

        # Should return at most 2 items
        assert len(data) <= 2