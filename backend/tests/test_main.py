from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings

settings = get_settings()
client = TestClient(app)

def test_health_ckeck():
    """
    Test that the /health endpoint returns 200 OK and correct JSON.
    """

    response = client.get("/health")

    assert response.status_code == 200

    assert response.json() == {"status": "ok", "service" : "Notification Service"}


def test_missing_api_key():
    """
    Test that protected endpoints return 401 if API key is missing.
    """
    response = client.post(
        "/notifications/email",
        json={
            "recipient": "test@example.com",
            "subject": "Test",
            "body": "Test body"
        }
    )

    assert response.status_code == 401
    assert "API key is missing" in response.json()["detail"]


def test_invalid_api_key():
    """
    Test that protected endpoints return 401 if API key is invalid.
    """
    response = client.post(
        "/notifications/email",
        headers={"X-API-Key": "wrong-key"},
        json={
            "recipient": "test@example.com",
            "subject": "Test",
            "body": "Test body"
        }
    )

    assert response.status_code == 401
    assert "Invalid API key" in response.json()["detail"]


def test_valid_api_key():
    """
    Test that protected endpoint works with correct API key.
    """
    response = client.post(
        "/notifications/email",
        headers={"X-API-Key": settings.api_key},
        json={
            "recipient": "test@example.com",
            "subject": "Test",
            "body": "Test body"
        }
    )

    assert response.status_code in [200, 429]