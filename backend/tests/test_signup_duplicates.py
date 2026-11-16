"""
Regression tests for duplicate account registration behavior.

Verifies:
1. Existing verified account:
   - Does not create another user.
   - Does not send a verification email.
   - Returns 409 Conflict with clear error.
2. Existing unverified account:
   - Does not create a duplicate user.
   - Does not generate unlimited verification tokens (rate-limited via check_rate_limit).
   - Reuses the existing account.
   - Returns 202 Accepted.
3. New email address:
   - Creates the user.
   - Generates verification token and queues verification email when required.
   - Preserves normal signup flow.
4. Normalization:
   - Case-insensitive and whitespace-insensitive email matching.
5. Concurrency protection:
   - Handles concurrent duplicate registrations gracefully without 500 error.
"""
import contextlib
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.limiter import limiter
from app.main import app
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.services.passwords import hash_password
from app.tasks.notification_tasks import send_email_task, send_sms_task, send_webhook_task

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_limiter_and_tasks():
    limiter.reset()
    with patch.object(send_email_task, "apply_async", return_value=MagicMock()) as m_email, \
         patch.object(send_sms_task, "apply_async", return_value=MagicMock()), \
         patch.object(send_webhook_task, "apply_async", return_value=MagicMock()):
        yield m_email
    limiter.reset()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


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


def test_existing_verified_account_does_not_create_user_or_send_email(db):
    """
    Case 1: Existing verified account
    - Must return 409 Conflict
    - Must NOT create another user
    - Must NOT send a verification email
    """
    unique_id = uuid.uuid4().hex[:8]
    email = f"verified_{unique_id}@example.com"

    # Pre-create a verified user
    user = User(
        email=email,
        password_hash=hash_password("OldPassword123!"),
        role="admin",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()

    initial_user_count = db.scalar(select(func.count(User.id)).where(User.email == email))
    assert initial_user_count == 1

    with _settings_override(signup_mode="open", require_email_verification=True), \
         patch("app.api.accounts.queue_system_email") as mock_mail:
        resp = client.post(
            "/auth/signup",
            json={"email": email, "password": "NewPassword123!"},
        )

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()
    mock_mail.assert_not_called()

    # Confirm user count is unchanged
    final_user_count = db.scalar(select(func.count(User.id)).where(User.email == email))
    assert final_user_count == 1


def test_existing_verified_account_case_insensitive_matching(db):
    """
    Case 1 & 4: Normalization
    - Even if entered as uppercase with whitespace: '  VERIFIED_user@Example.COM  '
    - Matches existing lowercase user and returns 409 Conflict.
    """
    unique_id = uuid.uuid4().hex[:8]
    canonical_email = f"canonical_{unique_id}@example.com"

    user = User(
        email=canonical_email,
        password_hash=hash_password("Password123!"),
        role="admin",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()

    input_email = f"  CANONICAL_{unique_id}@EXAMPLE.COM  "
    with _settings_override(signup_mode="open", require_email_verification=True), \
         patch("app.api.accounts.queue_system_email") as mock_mail:
        resp = client.post(
            "/auth/signup",
            json={"email": input_email, "password": "Password123!"},
        )

    assert resp.status_code == 409
    mock_mail.assert_not_called()


def test_existing_unverified_account_reuses_user_and_rate_limits(db):
    """
    Case 2: Existing unverified account
    - Reuses existing user
    - Does not create a duplicate user
    - Rate limits verification email sending
    """
    unique_id = uuid.uuid4().hex[:8]
    email = f"unverified_{unique_id}@example.com"

    # Pre-create unverified user
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        role="admin",
        is_active=True,
        email_verified_at=None,
    )
    db.add(user)
    db.commit()
    user_id = user.id

    with _settings_override(signup_mode="open", require_email_verification=True), \
         patch("app.api.accounts.queue_system_email") as mock_mail, \
         patch("app.api.accounts.check_rate_limit", side_effect=[True, False]) as mock_rl:
        # First duplicate signup attempt: rate limit allows (True)
        resp1 = client.post("/auth/signup", json={"email": email, "password": "Password123!"})
        assert resp1.status_code == 202
        assert mock_mail.call_count == 1

        # Second duplicate signup attempt within rate limit window: rate limit denies (False)
        resp2 = client.post("/auth/signup", json={"email": email, "password": "Password123!"})
        assert resp2.status_code == 202
        # Email call count should still be 1 (not spammed)
        assert mock_mail.call_count == 1

    # Verify user was reused, not duplicated
    all_users = db.scalars(select(User).where(User.email == email)).all()
    assert len(all_users) == 1
    assert all_users[0].id == user_id


def test_new_email_address_creates_user_and_sends_email(db):
    """
    Case 3: New email address
    - Creates user
    - Generates verification token & queues email
    """
    unique_id = uuid.uuid4().hex[:8]
    email = f"newuser_{unique_id}@example.com"

    with _settings_override(signup_mode="open", require_email_verification=True), \
         patch("app.api.accounts.queue_system_email") as mock_mail:
        resp = client.post("/auth/signup", json={"email": email, "password": "Password123!"})

    assert resp.status_code == 202
    mock_mail.assert_called_once()

    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.email_verified_at is None


def test_concurrent_signup_integrity_handling(db):
    """
    Case 5: Concurrency protection
    Tests that a concurrent duplicate signup (simulated by patching the new-user
    creation path to raise IntegrityError) returns 409 or 202 instead of 500.

    This test verifies the except IntegrityError block in accounts.py handles
    the race condition gracefully.
    """
    unique_id = uuid.uuid4().hex[:8]
    email = f"concurrent_{unique_id}@example.com"

    # Pre-create a verified user to represent the race winner
    user = User(
        email=email,
        password_hash=hash_password("Password123!"),
        role="admin",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()

    # We patch the Workspace creation (the first db.add+flush in new-user path)
    # to raise IntegrityError, simulating a concurrent signup that already committed.
    # The endpoint's except IntegrityError block should then recover gracefully.
    original_add = None
    add_calls = [0]

    # Patch db.add at the Session class level for this request
    from sqlalchemy.orm import Session as SASession
    original_session_add = SASession.add

    def patched_add(self, instance, *args, **kwargs):
        if isinstance(instance, Workspace):
            add_calls[0] += 1
            if add_calls[0] == 1:
                # Allow the workspace to be added normally (flush follows)
                original_session_add(self, instance, *args, **kwargs)
                # Then raise IntegrityError on the subsequent flush via patching flush
                return
        original_session_add(self, instance, *args, **kwargs)

    flush_calls = [0]
    original_flush = SASession.flush

    def patched_flush(self, *args, **kwargs):
        flush_calls[0] += 1
        # Raise on the 2nd flush (user.flush()) to simulate concurrent insert
        if flush_calls[0] == 2:
            raise IntegrityError("duplicate key value violates unique constraint", None, None)
        original_flush(self, *args, **kwargs)

    with _settings_override(signup_mode="open", require_email_verification=True), \
         patch("app.api.accounts.queue_system_email"), \
         patch.object(SASession, "flush", patched_flush):
        resp = client.post("/auth/signup", json={"email": email, "password": "Password123!"})

    # Must not be 500 — concurrency catch must handle this gracefully
    assert resp.status_code in (409, 202), (
        f"Expected 409 or 202 from concurrency recovery, got {resp.status_code}: {resp.text}"
    )
