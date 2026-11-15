"""
Regression tests: prove that test database isolation is correctly enforced.

These tests verify:
- pytest is running against notification_test_db, not notification_db
- TEST_DATABASE_URL is set and points to a test database
- The runtime SQLAlchemy engine is connected to the correct database
- Destructive helpers always operate on the test database
"""

import os

import pytest
from sqlalchemy import text


def test_test_database_url_is_set():
    """TEST_DATABASE_URL env var must be present."""
    url = os.environ.get("TEST_DATABASE_URL", "")
    assert url, (
        "TEST_DATABASE_URL is not set. "
        "pytest must be run with TEST_DATABASE_URL pointing to notification_test_db."
    )


def test_test_database_url_is_not_production():
    """TEST_DATABASE_URL must NOT point to notification_db or other prod databases."""
    from urllib.parse import urlparse

    url = os.environ.get("TEST_DATABASE_URL", "")
    db_name = urlparse(url).path.lstrip("/")
    forbidden = {"notification_db", "devcollab", "neondb", "postgres"}
    assert db_name not in forbidden, (
        f"TEST_DATABASE_URL points to '{db_name}', which is a production database."
    )
    assert "test" in db_name.lower(), (
        f"TEST_DATABASE_URL points to '{db_name}' — the name must contain 'test'."
    )


def test_sqlalchemy_engine_uses_test_database():
    """The module-level app.database.engine must point to the test database."""
    from app.database import engine

    db_name = engine.url.database or ""
    assert "test" in db_name.lower(), (
        f"app.database.engine is connected to '{db_name}', not a test database."
    )
    assert db_name != "notification_db", (
        "app.database.engine is still pointing to notification_db — isolation failed."
    )


def test_session_fixture_uses_test_database(db):
    """The 'db' fixture must yield a session connected to the test database."""
    result = db.execute(text("SELECT current_database()")).scalar()
    assert "test" in result.lower(), (
        f"db fixture is connected to '{result}', not a test database."
    )
    assert result != "notification_db", (
        f"db fixture is connected to notification_db — isolation failed."
    )


def test_notification_db_name_not_in_active_connection(db):
    """Explicit check: the string 'notification_db' (without _test) is not the DB."""
    result = db.execute(text("SELECT current_database()")).scalar()
    # 'notification_test_db' contains 'notification_db' as a substring, so check exactly
    assert result != "notification_db", (
        "Active connection is to notification_db — this would wipe real user data."
    )


def test_reset_db_guard_would_reject_non_test_db(monkeypatch):
    """
    Simulate what happens when _reset_db() is called with a non-test engine.

    We monkeypatch app.database.engine.url.database to a forbidden value and
    confirm that _reset_db() raises RuntimeError before executing any SQL.
    """
    import app.database as _db_module
    from sqlalchemy import create_engine
    from tests.test_journey import _reset_db

    # Build a fake engine whose URL.database is 'notification_db'
    fake_engine = create_engine("postgresql://x:y@localhost:5432/notification_db")
    original_engine = _db_module.engine
    monkeypatch.setattr(_db_module, "engine", fake_engine)
    try:
        with pytest.raises(RuntimeError, match="notification_db"):
            _reset_db()
    finally:
        monkeypatch.setattr(_db_module, "engine", original_engine)


def test_default_workspace_exists_in_test_db(db):
    """The default workspace that tests depend on must exist in the test database."""
    from sqlalchemy import text

    result = db.execute(
        text("SELECT slug FROM workspaces WHERE slug = 'default'")
    ).fetchone()
    assert result is not None, (
        "No 'default' workspace found in the test database. "
        "Run: python scripts/setup_test_db.py"
    )

