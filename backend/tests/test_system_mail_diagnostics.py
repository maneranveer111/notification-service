import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.config import Settings
from app.services.email_service import (
    _sanitize_error_str,
    _send_brevo,
    mask_email,
)
from app.services.errors import PermanentError, TransientError
from app.services.providers import BrevoConfig
from app.services.system_mail import queue_system_email
from app.tasks.notification_tasks import queue_for
from app.tasks.system_tasks import send_system_email_task


def _mock_settings(**kwargs):
    defaults = {
        "system_mail_backend": "provider",
        "celery_queue": "notification_service_dev",
        "email_provider_order": "brevo",
        "brevo_api_key": "xkeysib-mocksecretkey123456",
        "brevo_from_email": "noreply@example.com",
        "brevo_from_name": "Test Service",
        "database_url": "postgresql://mock",
        "api_key": "test_api_key",
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def test_mask_email_utility():
    assert mask_email("alice@example.com") == "a***e@example.com"
    assert mask_email("bob@example.com") == "b***b@example.com"
    assert mask_email("ab@example.com") == "a*@example.com"
    assert mask_email("a@example.com") == "*@example.com"
    assert mask_email("") == "***"
    assert mask_email(None) == "***"
    assert mask_email("invalid") == "***"


def test_sanitize_error_str():
    raw = "Brevo error: api-key=xkeysib-123456789abcdef token=eyJhbGciOiJIUzI1NiIn"
    sanitized = _sanitize_error_str(raw)
    assert "xkeysib" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized or "[REDACTED]" in sanitized
    assert "eyJhbGci" not in sanitized


def test_queue_system_email_routing_and_logging(caplog):
    mock_async_result = MagicMock()
    mock_async_result.id = "mock-task-uuid-1234"

    with patch("app.services.system_mail.send_system_email_task.apply_async", return_value=mock_async_result) as mock_apply, \
         caplog.at_level(logging.INFO, logger="app.services.system_mail"):
        queue_system_email("user@example.com", "Verify Email", "Click here")

        mock_apply.assert_called_once()
        _, kwargs = mock_apply.call_args
        assert kwargs["args"] == ["user@example.com", "Verify Email", "Click here"]
        assert kwargs["queue"] == queue_for("normal")

    assert any("Enqueued system email task" in r.message for r in caplog.records)
    assert any("mock-task-uuid-1234" in r.message for r in caplog.records)
    assert any("u***r@example.com" in r.message for r in caplog.records)


def test_queue_system_email_handles_enqueue_failure(caplog):
    with patch("app.services.system_mail.send_system_email_task.apply_async", side_effect=ConnectionError("Redis down")), \
         caplog.at_level(logging.ERROR, logger="app.services.system_mail"):
        # Must not raise an unhandled exception to keep API contract safe
        queue_system_email("user@example.com", "Verify Email", "Click here")

    assert any("Failed to enqueue system email" in r.message for r in caplog.records)
    assert any("u***r@example.com" in r.message for r in caplog.records)


def test_console_mode_does_not_call_providers(caplog):
    mock_settings = _mock_settings(system_mail_backend="console")
    with patch("app.tasks.system_tasks.get_settings", return_value=mock_settings), \
         patch("app.tasks.system_tasks.email_service.send_email") as mock_send, \
         caplog.at_level(logging.INFO, logger="app.tasks.system_tasks"):
        send_system_email_task.run("user@example.com", "Verify Email", "Body text")

        mock_send.assert_not_called()

    assert any("System email task received" in r.message for r in caplog.records)
    assert any("CONSOLE MAIL" in r.message for r in caplog.records)


def test_provider_mode_calls_brevo_and_logs_status_and_message_id(caplog):
    mock_settings = _mock_settings(system_mail_backend="provider")
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"messageId": "<brevo-msg-id-9999>"}

    with patch("app.tasks.system_tasks.get_settings", return_value=mock_settings), \
         patch("app.services.email_service.get_settings", return_value=mock_settings), \
         patch("requests.post", return_value=mock_response) as mock_post, \
         caplog.at_level(logging.INFO):
        send_system_email_task.run("user@example.com", "Verify Email", "Body text")

        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        json_data = mock_post.call_args[1]["json"]
        headers = mock_post.call_args[1]["headers"]

        assert "api.brevo.com" in url
        assert json_data["to"] == [{"email": "user@example.com"}]
        assert json_data["sender"]["email"] == "noreply@example.com"
        assert json_data["subject"] == "Verify Email"
        assert json_data["textContent"] == "Body text"
        assert headers["api-key"] == "xkeysib-mocksecretkey123456"

    # Verify diagnostic logs
    all_logs = " ".join(r.message for r in caplog.records)
    assert "System email task received" in all_logs
    assert "Provider request attempted" in all_logs
    assert "Brevo API response status=201" in all_logs
    assert "<brevo-msg-id-9999>" in all_logs
    assert "u***r@example.com" in all_logs


def test_provider_mode_brevo_auth_failure_logs_diagnostic(caplog):
    mock_settings = _mock_settings(system_mail_backend="provider")
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = '{"code": "unauthorized", "message": "Key not found"}'

    with patch("app.tasks.system_tasks.get_settings", return_value=mock_settings), \
         patch("app.services.email_service.get_settings", return_value=mock_settings), \
         patch("requests.post", return_value=mock_response), \
         caplog.at_level(logging.INFO):
        send_system_email_task.run("user@example.com", "Verify Email", "Body text")

    all_logs = " ".join(r.message for r in caplog.records)
    assert "Brevo auth error 401" in all_logs
    assert "Permanent failure sending system email" in all_logs
    assert "u***r@example.com" in all_logs
    # Ensure API key is NOT leaked in log
    assert "xkeysib-mocksecretkey123456" not in all_logs


def test_provider_mode_brevo_client_error_logs_diagnostic(caplog):
    mock_settings = _mock_settings(system_mail_backend="provider")
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = '{"code": "invalid_parameter", "message": "Sender email not valid"}'

    with patch("app.tasks.system_tasks.get_settings", return_value=mock_settings), \
         patch("app.services.email_service.get_settings", return_value=mock_settings), \
         patch("requests.post", return_value=mock_response), \
         caplog.at_level(logging.INFO):
        send_system_email_task.run("user@example.com", "Verify Email", "Body text")

    all_logs = " ".join(r.message for r in caplog.records)
    assert "Brevo client error 400" in all_logs
    assert "Permanent failure sending system email" in all_logs
    assert "u***r@example.com" in all_logs

