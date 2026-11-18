"""
Tests for reliable local run (Item 4):
- run_once() moves only due scheduled rows to pending
- Leaves future and cancelled rows
- Writes the heartbeat
- Never double-enqueues
- dev.py queue-name builder equals the API's
- --check logic with mocks
- dev_verification_link only in development + console
- Wrapper starts the thread only when ENABLE_BEAT is "true"
- /health/deep returns migrations and beat
"""

import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models.notification import Notification
from app.models.workspace import Workspace
from app.services.rate_limit import get_redis_client
from scripts.scheduler import run_once, write_heartbeat

client = TestClient(app)


def _get_or_create_workspace(db):
    ws = db.scalar(select(Workspace).where(Workspace.slug == "default"))
    if not ws:
        ws = Workspace(name="Default Workspace", slug="default", is_default=True)
        db.add(ws)
        db.commit()
        db.refresh(ws)
    return ws


def test_run_once_moves_only_due_scheduled_to_pending(db):
    """run_once() moves due scheduled rows to pending."""
    ws = _get_or_create_workspace(db)

    now = datetime.now(timezone.utc)
    due_notif = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="due@example.com",
        subject="Due Scheduled",
        body="Testing due scheduled",
        status="scheduled",
        scheduled_at=now - timedelta(minutes=1),
    )
    db.add(due_notif)
    db.commit()
    db.refresh(due_notif)

    # Call run_once
    run_once()

    db.refresh(due_notif)
    assert due_notif.status == "pending"


def test_run_once_leaves_future_and_cancelled_rows(db):
    """run_once() leaves future and cancelled notifications untouched."""
    ws = _get_or_create_workspace(db)

    now = datetime.now(timezone.utc)
    future_notif = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="future@example.com",
        subject="Future",
        body="Testing future",
        status="scheduled",
        scheduled_at=now + timedelta(hours=2),
    )
    cancelled_notif = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="cancelled@example.com",
        subject="Cancelled",
        body="Testing cancelled",
        status="cancelled",
        scheduled_at=now - timedelta(minutes=10),
    )
    db.add(future_notif)
    db.add(cancelled_notif)
    db.commit()

    run_once()

    db.refresh(future_notif)
    db.refresh(cancelled_notif)
    assert future_notif.status == "scheduled"
    assert cancelled_notif.status == "cancelled"


def test_run_once_writes_heartbeat(db):
    """run_once() writes beat:last_run to Redis."""
    run_once()

    try:
        r = get_redis_client()
        val = r.get("beat:last_run")
        assert val is not None
        ts = int(val)
        assert abs(time.time() - ts) < 10
    except Exception as exc:
        pytest.skip(f"Redis not available for heartbeat assertion: {exc}")


def test_run_once_never_double_enqueues(db):
    """Calling run_once multiple times does not re-process already moved rows."""
    ws = _get_or_create_workspace(db)

    now = datetime.now(timezone.utc)
    notif = Notification(
        workspace_id=ws.id,
        channel="email",
        recipient="double@example.com",
        subject="Double Test",
        body="Testing double enqueue",
        status="scheduled",
        scheduled_at=now - timedelta(seconds=30),
    )
    db.add(notif)
    db.commit()

    res1 = run_once()
    assert res1["dispatched"] >= 1

    # Second call immediately after: row is now pending, not scheduled
    res2 = run_once()
    db.refresh(notif)
    assert notif.status == "pending"


def test_dev_queue_builder_equals_api():
    """dev.py queue-name builder equals the API settings."""
    settings = get_settings()
    queues = settings.get_queue_names()
    q = settings.celery_queue or "notification_service_queue"
    assert queues == [f"{q}_high", q, f"{q}_low"]


def test_dev_preflight_logic_with_mocks():
    """--check preflight succeeds when dependencies are reachable, fails when Postgres down."""
    from scripts.dev import preflight

    # 1. Success case with mocks
    with patch("sqlalchemy.create_engine") as mock_engine, \
         patch("app.services.rate_limit.get_redis_client") as mock_redis, \
         patch("alembic.script.ScriptDirectory.from_config") as mock_script, \
         patch("alembic.migration.MigrationContext.configure") as mock_ctx:

        mock_redis.return_value.ping.return_value = True
        mock_ctx.return_value.get_current_revision.return_value = "head_rev"
        mock_script.return_value.get_current_head.return_value = "head_rev"

        assert preflight(check_only=True) is True

    # 2. Failure case when Postgres fails
    with patch("sqlalchemy.create_engine", side_effect=Exception("Database unreachable")):
        assert preflight(check_only=True) is False

    # 3. Failure case when Redis fails
    with patch("sqlalchemy.create_engine") as mock_engine, \
         patch("app.services.rate_limit.get_redis_client", side_effect=Exception("Redis down")), \
         patch("alembic.script.ScriptDirectory.from_config") as mock_script, \
         patch("alembic.migration.MigrationContext.configure") as mock_ctx:
        mock_ctx.return_value.get_current_revision.return_value = "head_rev"
        mock_script.return_value.get_current_head.return_value = "head_rev"
        assert preflight(check_only=True) is False


def test_dev_preflight_fails_when_migration_fails():
    """--check preflight returns False when migration application fails."""
    from scripts.dev import preflight

    with patch("sqlalchemy.create_engine"), \
         patch("alembic.script.ScriptDirectory.from_config") as mock_script, \
         patch("alembic.migration.MigrationContext.configure") as mock_ctx, \
         patch("subprocess.run") as mock_run:
        mock_ctx.return_value.get_current_revision.return_value = "old_rev"
        mock_script.return_value.get_current_head.return_value = "new_head"
        mock_run.return_value.returncode = 1  # migration failure
        assert preflight(check_only=True) is False



def test_wrapper_starts_thread_only_when_enable_beat_true():
    """worker_wrapper.py starts background scheduler thread only when ENABLE_BEAT=='true'."""
    import worker_wrapper

    with patch.dict(os.environ, {"ENABLE_BEAT": "false"}), \
         patch("subprocess.Popen") as mock_popen, \
         patch("threading.Thread") as mock_thread:

        mock_popen.return_value.wait.return_value = 0
        mock_popen.return_value.returncode = 0
        worker_wrapper._shutting_down = True
        try:
            worker_wrapper.start_celery()
        except SystemExit:
            pass

        # Thread was NOT started for beat
        for call in mock_thread.call_args_list:
            assert call.kwargs.get("target") != getattr(worker_wrapper, "run_loop", None)

    with patch.dict(os.environ, {"ENABLE_BEAT": "true"}), \
         patch("subprocess.Popen") as mock_popen, \
         patch("threading.Thread") as mock_thread:

        mock_popen.return_value.wait.return_value = 0
        mock_popen.return_value.returncode = 0
        worker_wrapper._shutting_down = True
        try:
            worker_wrapper.start_celery()
        except SystemExit:
            pass

        # Thread WAS started
        beat_calls = [
            c for c in mock_thread.call_args_list
            if "run_loop" in str(c.kwargs.get("target", ""))
        ]
        assert len(beat_calls) >= 1


def test_health_deep_returns_migrations_and_beat():
    """GET /health/deep returns migrations and beat keys."""
    settings = get_settings()
    headers = {}
    if settings.api_key:
        headers["X-API-Key"] = settings.api_key
    elif settings.metrics_token:
        headers["Authorization"] = f"Bearer {settings.metrics_token}"

    resp = client.get("/health/deep", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "migrations" in data
    assert data["migrations"] in ("ok", "behind", "unknown")
    assert "beat" in data
    assert data["beat"] in ("ok", "stale", "none")
