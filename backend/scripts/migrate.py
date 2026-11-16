"""Database migration runner with connection retries, session cleanup, and watchdog."""

import datetime
import os
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
STALE_SESSIONS_SQL = """
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND state IN ('idle in transaction', 'idle in transaction (aborted)')
  AND state_change < clock_timestamp() - interval '30 seconds';
"""

BLOCKER_ACTIVITY_SQL = """
SELECT pid, state, wait_event_type, wait_event,
       clock_timestamp() - state_change AS age,
       left(query, 100) AS query
FROM pg_stat_activity
WHERE datname = current_database();
"""

BLOCKER_PIDS_SQL = """
SELECT pid, unnest(pg_blocking_pids(pid)) AS blocking_pid
FROM pg_stat_activity
WHERE datname = current_database();
"""


def _log(msg: str) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{now}] {msg}", flush=True)


def mask_url(url: str) -> str:
    """Mask password in a database connection URL."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username or ''}:****@{parsed.hostname or ''}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse((
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            ))
        return url
    except Exception:
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)


def build_pgoptions() -> str:
    """Build PGOPTIONS enforcing statement and lock timeouts."""
    return "-c lock_timeout=30000 -c statement_timeout=300000 -c idle_in_transaction_session_timeout=120000"


def wait_for_database(db_url: str, max_seconds: int = 60, interval: int = 2) -> None:
    """Attempt connecting with SELECT 1 every interval seconds until max_seconds."""
    _log("Waiting for database to become reachable...")
    start_time = time.monotonic()
    last_error = ""

    while time.monotonic() - start_time < max_seconds:
        try:
            temp_engine = create_engine(
                db_url,
                connect_args={"connect_timeout": 2},
                pool_pre_ping=False,
            )
            with temp_engine.connect() as conn:
                conn.execute(text("SELECT 1;"))
            temp_engine.dispose()
            _log("Database connection established.")
            return
        except Exception as e:
            last_error = mask_url(str(e))
            time.sleep(interval)

    _log(f"Database unreachable after {max_seconds} seconds: {last_error}")
    sys.exit(2)


def kill_stale_sessions(engine) -> int:
    """Terminate idle in transaction sessions older than 30 seconds."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(STALE_SESSIONS_SQL))
            rows = result.fetchall()
            count = len(rows)
            conn.commit()
            return count
    except Exception as e:
        _log(f"Warning: Failed to terminate stale sessions: {mask_url(str(e))}")
        return 0


def format_blocker_report(engine) -> str:
    """Format contents of pg_stat_activity and pg_blocking_pids."""
    lines = ["--- Database Blocker Report ---"]
    try:
        with engine.connect() as conn:
            lines.append("Active sessions in current database:")
            activities = conn.execute(text(BLOCKER_ACTIVITY_SQL)).fetchall()
            if activities:
                for row in activities:
                    pid, state, wait_type, wait_event, age, q = row
                    safe_query = (q or "").replace("\n", " ").strip()[:100]
                    safe_query = mask_url(safe_query)
                    lines.append(
                        f"  pid={pid} state={state} wait={wait_type}/{wait_event} age={age} query={safe_query}"
                    )
            else:
                lines.append("  (no active sessions)")

            lines.append("Blocking PIDs:")
            blockers = conn.execute(text(BLOCKER_PIDS_SQL)).fetchall()
            if blockers:
                for b_pid, blocking_pid in blockers:
                    lines.append(f"  pid={b_pid} is blocked by pid={blocking_pid}")
            else:
                lines.append("  (no blocking relationships found)")
    except Exception as e:
        lines.append(f"  Failed to query pg_stat_activity: {mask_url(str(e))}")

    lines.append("-------------------------------")
    return "\n".join(lines)


def run_watchdog(engine, timeout_seconds: int = 240) -> None:
    """Background watchdog timer that terminates the process if hung."""
    def _timeout_handler():
        _log(f"FATAL: Migration watchdog timed out after {timeout_seconds}s!")
        print(format_blocker_report(engine), flush=True)
        os._exit(4)

    t = threading.Timer(timeout_seconds, _timeout_handler)
    t.daemon = True
    t.start()


def main() -> None:
    from app.config import get_settings
    settings = get_settings()
    db_url = settings.database_url

    masked = mask_url(db_url)
    _log(f"Migration runner starting. Target database: {masked}")

    # 1. Wait for database
    wait_for_database(db_url, max_seconds=60, interval=2)

    # 2. Set PGOPTIONS
    pgoptions = build_pgoptions()
    os.environ["PGOPTIONS"] = pgoptions
    _log(f"Applied PGOPTIONS: {pgoptions}")

    engine = create_engine(db_url, pool_pre_ping=True)

    # 3. Terminate stale sessions if requested
    kill_enabled = os.environ.get("MIGRATE_KILL_STALE_SESSIONS", "").lower() in ("true", "1", "yes")
    if kill_enabled:
        terminated = kill_stale_sessions(engine)
        _log(f"Terminated {terminated} stale idle-in-transaction session(s).")
    else:
        _log("MIGRATE_KILL_STALE_SESSIONS is disabled.")

    # 4. Start watchdog
    run_watchdog(engine, timeout_seconds=240)

    # 5. Programmatic Alembic upgrade
    try:
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.migration import MigrationContext

        alembic_ini_path = ROOT_DIR / "alembic.ini"
        cfg = Config(str(alembic_ini_path))
        cfg.set_main_option("script_location", str(ROOT_DIR / "alembic"))
        cfg.set_main_option("sqlalchemy.url", db_url)

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current_rev = ctx.get_current_revision()
        
        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()

        _log(f"Current migration revision: {current_rev or 'None'} -> Target head: {head_rev}")

        _log("Executing Alembic upgrade head...")
        command.upgrade(cfg, "head")

        _log(f"Migrations complete (revision {head_rev}).")
        sys.exit(0)

    except Exception as e:
        _log(f"Migration failed with error: {mask_url(str(e))}")
        print(format_blocker_report(engine), flush=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
