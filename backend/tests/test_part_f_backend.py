"""Tests for Part F production startup validation.
"""
from cryptography.fernet import Fernet
import pytest

from app.config import Settings
from app.services.startup_checks import (
    check_production_settings,
    validate_production_or_raise,
)


def _make_valid_prod_settings(**kwargs) -> Settings:
    defaults = {
        "environment": "production",
        "database_url": "postgresql://postgres:secret@db:5432/notification_db",
        "redis_url": "redis://:secret@redis:6379/0",
        "api_key": "very-long-production-api-key-12345",
        "jwt_secret": "a" * 32,
        "encryption_key": Fernet.generate_key().decode(),
        "unsubscribe_secret": "secure_unsubscribe_secret_value",
        "system_mail_backend": "provider",
        "public_base_url": "https://api.example.com",
        "frontend_public_url": "https://notify.example.com",
        "signup_mode": "invite_only",
        "trusted_proxy_count": 2,
        "rate_limit_storage_uri": "redis://:secret@redis:6379/1",
        "metrics_token": "secure_metrics_bearer_token",
        "turnstile_secret_key": "turnstile_secret_key",
        "log_format": "json",
        "celery_queue": "notification_service_queue",
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def test_dev_mode_skips_everything():
    s = Settings(
        environment="development",
        database_url="postgresql://localhost/dev",
        api_key="test",
        jwt_secret=None,
        encryption_key=None,
    )
    errors, warnings = check_production_settings(s)
    assert errors == []
    assert warnings == []


def test_valid_production_config_passes():
    s = _make_valid_prod_settings()
    errors, warnings = check_production_settings(s)
    assert errors == []
    assert warnings == []


def test_jwt_secret_error():
    s1 = _make_valid_prod_settings(jwt_secret=None)
    errors1, _ = check_production_settings(s1)
    assert any("jwt_secret" in e for e in errors1)

    s2 = _make_valid_prod_settings(jwt_secret="short-key")
    errors2, _ = check_production_settings(s2)
    assert any("jwt_secret" in e for e in errors2)


def test_encryption_key_error():
    s1 = _make_valid_prod_settings(encryption_key=None)
    errors1, _ = check_production_settings(s1)
    assert any("encryption_key" in e for e in errors1)

    s2 = _make_valid_prod_settings(encryption_key="not-a-valid-fernet-key")
    errors2, _ = check_production_settings(s2)
    assert any("encryption_key" in e for e in errors2)

    # Comma-separated rotation keys with one invalid key
    valid_k = Fernet.generate_key().decode()
    s3 = _make_valid_prod_settings(encryption_key=f"{valid_k},invalid_key")
    errors3, _ = check_production_settings(s3)
    assert any("encryption_key" in e for e in errors3)


def test_api_key_error():
    s1 = _make_valid_prod_settings(api_key="")
    errors1, _ = check_production_settings(s1)
    assert any("api_key" in e for e in errors1)

    s2 = _make_valid_prod_settings(api_key="too-short")
    errors2, _ = check_production_settings(s2)
    assert any("api_key" in e for e in errors2)

    for placeholder in ["change-me", "changeme", "your-api-key", "ci-test-key", "test"]:
        s_p = _make_valid_prod_settings(api_key=placeholder)
        errors_p, _ = check_production_settings(s_p)
        assert any("api_key" in e for e in errors_p)


def test_unsubscribe_secret_error():
    s = _make_valid_prod_settings(unsubscribe_secret=None)
    errors, _ = check_production_settings(s)
    assert any("unsubscribe_secret" in e for e in errors)


def test_system_mail_backend_error():
    s = _make_valid_prod_settings(system_mail_backend="console")
    errors, _ = check_production_settings(s)
    assert any("system_mail_backend" in e for e in errors)


def test_urls_error_and_localhost_allowance():
    # Non-https on non-localhost is an error
    s1 = _make_valid_prod_settings(public_base_url="http://api.example.com")
    errors1, _ = check_production_settings(s1)
    assert any("public_base_url" in e for e in errors1)

    s2 = _make_valid_prod_settings(frontend_public_url="http://notify.example.com")
    errors2, _ = check_production_settings(s2)
    assert any("frontend_public_url" in e for e in errors2)

    # Localhost/127.0.0.1 can use http without error
    s3 = _make_valid_prod_settings(
        public_base_url="http://localhost:8001",
        frontend_public_url="http://127.0.0.1:3000",
    )
    errors3, _ = check_production_settings(s3)
    assert not any("public_base_url" in e for e in errors3)
    assert not any("frontend_public_url" in e for e in errors3)


def test_signup_mode_error():
    s = _make_valid_prod_settings(signup_mode="public")
    errors, _ = check_production_settings(s)
    assert any("signup_mode" in e for e in errors)


def test_warning_rules():
    s = _make_valid_prod_settings(
        trusted_proxy_count=0,
        rate_limit_storage_uri=None,
        metrics_token=None,
        signup_mode="open",
        turnstile_secret_key=None,
        log_format="text",
        celery_queue="notification_dev_queue",
        database_url="postgresql://postgres:secret@localhost:5432/notification_db",
    )
    errors, warnings = check_production_settings(s)
    assert errors == []
    warning_text = "\n".join(warnings)
    assert "trusted_proxy_count" in warning_text
    assert "rate_limit_storage_uri" in warning_text
    assert "metrics_token" in warning_text
    assert "turnstile_secret_key" in warning_text
    assert "log_format" in warning_text
    assert "celery_queue" in warning_text
    assert "database_url" in warning_text


def test_no_secret_values_in_messages():
    super_secret_jwt = "SUPER_SECRET_JWT_KEY_THAT_IS_TOO_SHORT"
    super_secret_api = "SUPER_SECRET_API_KEY_PH"
    s = _make_valid_prod_settings(
        jwt_secret=super_secret_jwt,
        api_key=super_secret_api,
    )
    errors, warnings = check_production_settings(s)
    combined = " ".join(errors + warnings)
    assert super_secret_jwt not in combined
    assert super_secret_api not in combined


def test_validate_production_or_raise():
    s = _make_valid_prod_settings(jwt_secret="short")
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_or_raise(s)
    assert "Invalid production configuration:" in str(exc_info.value)
    assert "- jwt_secret" in str(exc_info.value)
