"""
Unit tests for reset_dev_db safety refusal logic.

These tests execute without touching any database.
"""

import pytest
from scripts.reset_dev_db import validate_safety, reset_dev_db


def test_refuse_remote_host():
    """validate_safety refuses when database host is remote."""
    with pytest.raises(ValueError, match="is not a local host"):
        validate_safety("postgresql://user:pass@remotehost:5432/mydb", "development")


def test_refuse_prod_dbname():
    """validate_safety refuses when database name contains 'prod'."""
    with pytest.raises(ValueError, match="contains 'prod'"):
        validate_safety("postgresql://user:pass@localhost:5432/notification_prod_db", "development")


def test_refuse_production_environment():
    """validate_safety refuses when environment is 'production'."""
    with pytest.raises(ValueError, match="ENVIRONMENT is set to 'production'"):
        validate_safety("postgresql://user:pass@localhost:5432/notification_dev", "production")


def test_refuse_without_yes_flag():
    """reset_dev_db refuses with exit code 2 when --yes is False."""
    with pytest.raises(SystemExit) as exc:
        reset_dev_db(yes=False)
    assert exc.value.code == 2


def test_safety_passes_for_local_dev():
    """validate_safety succeeds for valid localhost dev database."""
    # Should not raise
    validate_safety("postgresql://postgres:pass@localhost:5432/notification_dev", "development")
    validate_safety("postgresql://postgres:pass@127.0.0.1:5432/notification_dev", "development")
    validate_safety("postgresql://postgres:pass@::1:5432/notification_dev", "development")
