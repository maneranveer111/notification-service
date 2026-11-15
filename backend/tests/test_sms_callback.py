from unittest.mock import MagicMock, patch
import pytest

from app.services.providers import TwilioConfig
from app.services.sms_service import is_valid_public_callback_url, send_sms


def _create_twilio_config(status_callback: str | None = None) -> TwilioConfig:
    return TwilioConfig(
        account_sid="ACmockaccount12345678901234567890",
        auth_token="mockauthtoken123456789012345678",
        from_number="+15551234567",
        status_callback=status_callback,
    )


def test_is_valid_public_callback_url_utility():
    # Loopback / local development URLs must return False
    assert is_valid_public_callback_url("http://localhost:8001/webhooks/twilio") is False
    assert is_valid_public_callback_url("http://localhost/webhooks/twilio") is False
    assert is_valid_public_callback_url("https://localhost:8001/webhooks/twilio") is False
    assert is_valid_public_callback_url("http://127.0.0.1:8001/webhooks/twilio") is False
    assert is_valid_public_callback_url("http://127.0.0.1/webhooks/twilio/token") is False
    assert is_valid_public_callback_url("http://0.0.0.0:8001/webhooks/twilio") is False
    assert is_valid_public_callback_url("http://[::1]:8001/webhooks/twilio") is False

    # Public HTTPS / ngrok URLs must return True
    assert is_valid_public_callback_url("https://api.example.com/webhooks/twilio") is True
    assert is_valid_public_callback_url("https://xyz-abc.ngrok-free.app/webhooks/twilio/tok_123") is True
    assert is_valid_public_callback_url("https://tunnel.example.org:8443/webhooks/twilio") is True
    assert is_valid_public_callback_url("http://public-server.com/webhooks/twilio") is True

    # Missing or invalid inputs must return False
    assert is_valid_public_callback_url(None) is False
    assert is_valid_public_callback_url("") is False
    assert is_valid_public_callback_url("   ") is False
    assert is_valid_public_callback_url("not-a-url") is False
    assert is_valid_public_callback_url("ftp://example.com/callback") is False


def test_send_sms_omits_localhost_callback():
    cfg = _create_twilio_config(status_callback="http://localhost:8001/webhooks/twilio/workspace-token")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SMmock123")

    with patch("app.services.sms_service.Client", return_value=mock_client):
        sid = send_sms("+15559876543", "Hello local", config=cfg)
        assert sid == "SMmock123"

        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        assert "status_callback" not in kwargs
        assert kwargs["to"] == "+15559876543"
        assert kwargs["body"] == "Hello local"
        assert kwargs["from_"] == "+15551234567"


def test_send_sms_omits_127_0_0_1_callback():
    cfg = _create_twilio_config(status_callback="http://127.0.0.1:8001/webhooks/twilio/workspace-token")
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SMmock123")

    with patch("app.services.sms_service.Client", return_value=mock_client):
        sid = send_sms("+15559876543", "Hello 127", config=cfg)
        assert sid == "SMmock123"

        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        assert "status_callback" not in kwargs


def test_send_sms_passes_public_https_callback():
    public_url = "https://api.notification.example.com/webhooks/twilio/workspace-token"
    cfg = _create_twilio_config(status_callback=public_url)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SMmock123")

    with patch("app.services.sms_service.Client", return_value=mock_client):
        sid = send_sms("+15559876543", "Hello prod", config=cfg)
        assert sid == "SMmock123"

        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["status_callback"] == public_url


def test_send_sms_passes_ngrok_https_callback():
    ngrok_url = "https://subdomain.ngrok-free.app/webhooks/twilio/workspace-token"
    cfg = _create_twilio_config(status_callback=ngrok_url)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SMmock123")

    with patch("app.services.sms_service.Client", return_value=mock_client):
        sid = send_sms("+15559876543", "Hello ngrok", config=cfg)
        assert sid == "SMmock123"

        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["status_callback"] == ngrok_url


def test_send_sms_handles_missing_callback_safely():
    cfg = _create_twilio_config(status_callback=None)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SMmock123")

    with patch("app.services.sms_service.Client", return_value=mock_client):
        sid = send_sms("+15559876543", "Hello none", config=cfg)
        assert sid == "SMmock123"

        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        assert "status_callback" not in kwargs

