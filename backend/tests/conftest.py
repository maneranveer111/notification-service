"""
Central pytest configuration — test database isolation.

IMPORTANT: pytest MUST be run with TEST_DATABASE_URL set to a dedicated test
database (e.g. notification_test_db).  The conftest fails fast at import time
if the env var is absent or points to a forbidden production database.

This file patches app.database.engine and app.database.SessionLocal BEFORE any
test module imports the application, so all tests automatically use the test DB.
"""

import os
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Fail-closed database guard (runs at import time, before any test)
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

if not TEST_DATABASE_URL:
    raise RuntimeError(
        "\n\n"
        "ERROR: TEST_DATABASE_URL is not set.\n"
        "pytest must only run against a dedicated test database.\n"
        "Example:\n"
        "  $env:TEST_DATABASE_URL = "
        "'postgresql://postgres:postgre123@localhost:5432/notification_test_db'\n"
        "  pytest -q\n"
    )

_parsed = urlparse(TEST_DATABASE_URL)
_dbname = _parsed.path.lstrip("/")

# Databases that must NEVER be used by tests
_FORBIDDEN_DBS = {"notification_db", "devcollab", "neondb", "postgres"}

if _dbname in _FORBIDDEN_DBS:
    raise RuntimeError(
        f"\n\nERROR: TEST_DATABASE_URL points to '{_dbname}', "
        "which is a production/development database.\n"
        "Refusing to run tests to protect real data.\n"
        "Set TEST_DATABASE_URL to a database whose name contains 'test'.\n"
    )

if "test" not in _dbname.lower():
    raise RuntimeError(
        f"\n\nERROR: TEST_DATABASE_URL points to '{_dbname}', "
        "which does not look like a test database (name must contain 'test').\n"
        "Refusing to run tests to protect real data.\n"
    )

# ---------------------------------------------------------------------------
# Patch app.database BEFORE any test module or application module loads it
# ---------------------------------------------------------------------------

import app.database as _db_module  # noqa: E402  (must come after guard above)

test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

# Replace the module-level singletons that every test and app code imports
_db_module.engine = test_engine
_db_module.SessionLocal = TestSessionLocal

# Import the FastAPI app AFTER patching the engine so the app sees the test DB
from app.main import app as _fastapi_app  # noqa: E402
from app.database import get_db  # noqa: E402


def _override_get_db():
    """FastAPI dependency override — yields a test-DB session."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


_fastapi_app.dependency_overrides[get_db] = _override_get_db

# ---------------------------------------------------------------------------
# Shared pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def db():
    """Provide a SQLAlchemy session connected to notification_test_db."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session", autouse=True)
def _verify_test_db_at_runtime():
    """
    Session-scoped sanity check: confirm the engine really points to the test
    database once connections are live (guards against env-var tricks that
    redirect after import time).
    """
    with test_engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database()")).scalar()
    assert "test" in db_name, (
        f"Runtime check failed: connected to '{db_name}', not a test database."
    )
    assert db_name != "notification_db", (
        "Runtime check failed: connected to notification_db — aborting."
    )

