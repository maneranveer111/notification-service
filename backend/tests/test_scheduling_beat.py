"""
Spec 3 tests: beat heartbeat, /health/deep beat key, dispatch_scheduled behaviour,
and compose file text assertions.
"""
import pathlib
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

ROOT = pathlib.Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Beat heartbeat is written and expires
# ---------------------------------------------------------------------------

class _FakeRedis:
    def __init__(self):
        self._store = {}

    def set(self, key, value, ex=None):
        self._store[key] = (value, ex)

    def get(self, key):
        entry = self._store.get(key)
        return str(entry[0]).encode() if entry else None

    def ping(self):
        return True

    def llen(self, key):
        return 0


def test_beat_heartbeat_written():
    """dispatch_scheduled stores an integer epoch in beat:last_run."""
    fake_redis = _FakeRedis()
    with (
        patch("app.services.rate_limit.get_redis_client", return_value=fake_redis),
        patch("app.tasks.notification_tasks.SessionLocal") as mock_sl,
    ):
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        mock_db.commit.return_value = None

        from app.tasks.notification_tasks import dispatch_scheduled
        dispatch_scheduled()

    assert "beat:last_run" in fake_redis._store
    val, ex = fake_redis._store["beat:last_run"]
    assert isinstance(val, int)
    assert val > 0
    assert ex == 600


def test_beat_heartbeat_expiry_set():
    """beat:last_run is stored with a 10-minute (600s) TTL."""
    fake_redis = _FakeRedis()
    with (
        patch("app.services.rate_limit.get_redis_client", return_value=fake_redis),
        patch("app.tasks.notification_tasks.SessionLocal") as mock_sl,
    ):
        mock_db = MagicMock()
        mock_sl.return_value = mock_db
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        mock_db.commit.return_value = None

        from app.tasks.notification_tasks import dispatch_scheduled
        dispatch_scheduled()

    _, ex = fake_redis._store["beat:last_run"]
    assert ex == 600


# ---------------------------------------------------------------------------
# 2. /health/deep beat field
# ---------------------------------------------------------------------------

@pytest.fixture()
def deep_client():
    from app.main import app, settings
    client = TestClient(app, raise_server_exceptions=False)
    return client, settings


def _auth_headers(settings):
    return {"X-API-Key": settings.api_key}


def test_health_deep_beat_ok(deep_client):
    client, settings = deep_client
    fresh_ts = int(time.time())
    fake_redis = _FakeRedis()
    fake_redis._store["beat:last_run"] = (fresh_ts, 600)
    with patch("app.services.rate_limit.get_redis_client", return_value=fake_redis):
        resp = client.get("/health/deep", headers=_auth_headers(settings))
    assert resp.status_code == 200
    assert resp.json()["beat"] == "ok"


def test_health_deep_beat_stale(deep_client):
    client, settings = deep_client
    old_ts = int(time.time()) - 200  # > 120 s ago
    fake_redis = _FakeRedis()
    fake_redis._store["beat:last_run"] = (old_ts, 600)
    with patch("app.services.rate_limit.get_redis_client", return_value=fake_redis):
        resp = client.get("/health/deep", headers=_auth_headers(settings))
    assert resp.status_code == 200
    assert resp.json()["beat"] == "stale"


def test_health_deep_beat_none(deep_client):
    client, settings = deep_client
    fake_redis = _FakeRedis()
    # No "beat:last_run" key
    with patch("app.services.rate_limit.get_redis_client", return_value=fake_redis):
        resp = client.get("/health/deep", headers=_auth_headers(settings))
    assert resp.status_code == 200
    assert resp.json()["beat"] == "none"


# ---------------------------------------------------------------------------
# 3. dispatch_scheduled moves only due rows, leaves future rows alone,
#    ignores cancelled rows
# ---------------------------------------------------------------------------

def test_dispatch_scheduled_moves_due_rows(db):
    """Due 'scheduled' rows become 'pending'; future rows stay 'scheduled'."""
    from app.models.notification import Notification
    from app.tasks.notification_tasks import dispatch_scheduled

    now = datetime.now(timezone.utc)

    due = Notification(
        channel="email",
        status="scheduled",
        scheduled_at=now - timedelta(seconds=5),
        priority="normal",
        recipient="due@example.com",
        workspace_id=None,
    )
    future = Notification(
        channel="email",
        status="scheduled",
        scheduled_at=now + timedelta(hours=1),
        priority="normal",
        recipient="future@example.com",
        workspace_id=None,
    )
    cancelled = Notification(
        channel="email",
        status="cancelled",
        scheduled_at=now - timedelta(seconds=5),
        priority="normal",
        recipient="cancelled@example.com",
        workspace_id=None,
    )
    db.add_all([due, future, cancelled])
    db.commit()

    fake_redis = _FakeRedis()
    with (
        patch("app.services.rate_limit.get_redis_client", return_value=fake_redis),
        patch("app.tasks.notification_tasks.enqueue_notification"),
    ):
        result = dispatch_scheduled()

    db.expire_all()
    assert result["status"] == "ok"
    assert result["dispatched_count"] == 1
    assert due.status == "pending"
    assert future.status == "scheduled"
    assert cancelled.status == "cancelled"


# ---------------------------------------------------------------------------
# 4. Compose file text assertions
# ---------------------------------------------------------------------------

def _read_compose(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_compose_dev_has_beat_schedule_flag():
    text = _read_compose("docker-compose.yml")
    assert "-B" in text
    assert "-s /tmp/celerybeat-schedule" in text


def test_compose_prod_has_beat_schedule_flag():
    text = _read_compose("docker-compose.prod.yml")
    assert "-B" in text
    assert "-s /tmp/celerybeat-schedule" in text


def test_compose_no_port_8000():
    for fname in ("docker-compose.yml", "docker-compose.prod.yml"):
        text = _read_compose(fname)
        bad_port = "80" + "00"
        assert f":{bad_port}" not in text
        assert f'"{bad_port}:' not in text
        assert f"'{bad_port}:" not in text
