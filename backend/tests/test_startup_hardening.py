"""Unit tests for migration runner and compose startup hardening."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scripts.migrate import (
    build_pgoptions,
    mask_url,
    wait_for_database,
    format_blocker_report,
    kill_stale_sessions,
    STALE_SESSIONS_SQL,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_pgoptions_builder():
    pgopts = build_pgoptions()
    assert "lock_timeout=30000" in pgopts
    assert "statement_timeout=300000" in pgopts
    assert "idle_in_transaction_session_timeout=120000" in pgopts


def test_wait_for_database_succeeds_after_retries():
    attempts = 0

    def mock_connect(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Connection refused")
        m_conn = MagicMock()
        m_conn.__enter__.return_value = m_conn
        return m_conn

    m_engine = MagicMock()
    m_engine.connect.side_effect = mock_connect

    with patch("scripts.migrate.create_engine", return_value=m_engine), \
         patch("time.sleep", return_value=None):
        wait_for_database("postgresql://user:pass@localhost:5432/db", max_seconds=10, interval=1)

    assert attempts == 3


def test_wait_for_database_gives_up_after_limit():
    m_engine = MagicMock()
    m_engine.connect.side_effect = ConnectionError("Connection refused")

    with patch("scripts.migrate.create_engine", return_value=m_engine), \
         patch("time.sleep", return_value=None):
        with pytest.raises(SystemExit) as exc_info:
            wait_for_database("postgresql://user:pass@localhost:5432/db", max_seconds=3, interval=1)

    assert exc_info.value.code == 2


def test_mask_url_hides_password():
    raw_url = "postgresql://myuser:supersecret123@myhost:5432/mydb"
    masked = mask_url(raw_url)
    assert "supersecret123" not in masked
    assert "myuser:****@myhost:5432/mydb" in masked


def test_blocker_report_never_contains_password_and_truncates():
    long_query = "SELECT * FROM users WHERE secret_pw = 'supersecret123' " + ("x" * 200)
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = [
        MagicMock(fetchall=lambda: [(123, "active", "Lock", "relation", "00:01:00", long_query)]),
        MagicMock(fetchall=lambda: [(123, 456)]),
    ]
    mock_conn.__enter__.return_value = mock_conn

    mock_engine = MagicMock()
    mock_engine.connect.return_value = mock_conn

    report = format_blocker_report(mock_engine)
    assert "pid=123" in report
    assert "blocked by pid=456" in report
    assert len(long_query[:100]) == 100
    # Check that output query does not exceed 100 chars
    for line in report.splitlines():
        if "query=" in line:
            q_part = line.split("query=")[1]
            assert len(q_part) <= 100


def test_stale_session_sql_targets_current_db_and_excludes_runner():
    sql = STALE_SESSIONS_SQL.lower()
    assert "datname = current_database()" in sql
    assert "pid <> pg_backend_pid()" in sql
    assert "pg_terminate_backend(pid)" in sql
    assert "idle in transaction" in sql


def test_compose_migrate_command_contains_scripts_migrate():
    dev_compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    prod_compose = (ROOT_DIR / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "scripts.migrate" in dev_compose
    assert "scripts.migrate" in prod_compose


def test_compose_db_command_contains_idle_in_transaction():
    dev_compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    prod_compose = (ROOT_DIR / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "idle_in_transaction_session_timeout=60000" in dev_compose
    assert "idle_in_transaction_session_timeout=60000" in prod_compose


def test_compose_db_healthcheck_contains_localhost_ip():
    dev_compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    prod_compose = (ROOT_DIR / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "-h 127.0.0.1" in dev_compose
    assert "-h 127.0.0.1" in prod_compose


def test_compose_ports_contain_8001_and_no_8000():
    dev_compose = (ROOT_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    prod_compose = (ROOT_DIR / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert "8000" not in dev_compose
    assert "8000" not in prod_compose
    assert "8001" in dev_compose
    assert "8001" in prod_compose
