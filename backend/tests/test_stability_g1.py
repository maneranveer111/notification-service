import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models.user import User
from app.services.jwt_tokens import create_access_token
from app.services.passwords import hash_password

client = TestClient(app)
settings = get_settings()


def _make_user(db, role="user", is_superadmin=False):
    email = f"u_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email.lower(),
        password_hash=hash_password("password123!"),
        role=role,
        is_superadmin=is_superadmin,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _token_for(user):
    return create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
    )


def test_deep_health_anonymous_401():
    resp = client.get("/health/deep")
    assert resp.status_code == 401


def test_deep_health_normal_user_403(db):
    normal_user = _make_user(db, is_superadmin=False)
    token = _token_for(normal_user)
    resp = client.get("/health/deep", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_deep_health_superadmin_200(db):
    super_user = _make_user(db, is_superadmin=True)
    token = _token_for(super_user)
    resp = client.get("/health/deep", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "db" in data
    assert "redis" in data
    assert "worker" in data
    assert "queues" in data
    assert "environment" in data
    assert "version" in data


def test_deep_health_metrics_token_200():
    token = settings.metrics_token or "dummy-metrics-token"
    orig_token = settings.metrics_token
    object.__setattr__(settings, "metrics_token", token)
    try:
        resp = client.get("/health/deep", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["environment"] == settings.environment
    finally:
        object.__setattr__(settings, "metrics_token", orig_token)


def test_deep_health_redis_error_handled_without_raising(db):
    super_user = _make_user(db, is_superadmin=True)
    token = _token_for(super_user)

    with patch("app.services.rate_limit.get_redis_client", side_effect=Exception("Redis down")):
        resp = client.get("/health/deep", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["redis"] == "error"


def test_deep_health_worker_none_when_ping_empty(db):
    super_user = _make_user(db, is_superadmin=True)
    token = _token_for(super_user)

    mock_inspect = MagicMock()
    mock_inspect.ping.return_value = None

    with patch("app.celery_app.celery.control.inspect", return_value=mock_inspect):
        resp = client.get("/health/deep", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["worker"] == "none"


def test_public_config_includes_environment_and_version():
    with patch.dict(os.environ, {"APP_VERSION": "v1.2.3"}):
        resp = client.get("/public/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["environment"] == settings.environment
        assert data["version"] == "v1.2.3"


def test_public_config_has_no_store_header():
    resp = client.get("/public/config")
    assert resp.status_code == 200
    assert "no-store" in resp.headers.get("Cache-Control", "")
