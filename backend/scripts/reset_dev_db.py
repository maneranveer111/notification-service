"""
Reset local development database and Redis.

SAFETY GUARDS:
- Refuses unless host is localhost, 127.0.0.1, or ::1
- Refuses if database name contains 'prod'
- Refuses if ENVIRONMENT is 'production'
- Requires --yes flag
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_safety(db_url: str, environment: str) -> None:
    """Validate safety rules. Raises ValueError with clear message if unsafe."""
    if not db_url:
        raise ValueError("DATABASE_URL is not set.")

    parsed = urlparse(db_url)
    raw_host = (parsed.hostname or "").lower()
    if not raw_host and "@" in db_url:
        after_at = db_url.split("@")[-1].split("/")[0]
        if after_at.startswith("::1"):
            raw_host = "::1"
    host = raw_host.strip("[]")
    dbname = (parsed.path or "").lstrip("/").lower()
    env = (environment or "").lower()

    if host not in ALLOWED_HOSTS:
        raise ValueError(
            f"REFUSAL: Database host '{host}' is not a local host (allowed: {ALLOWED_HOSTS})."
        )

    if "prod" in dbname:
        raise ValueError(
            f"REFUSAL: Database name '{dbname}' contains 'prod'. Cannot reset production database."
        )

    if env == "production":
        raise ValueError(
            "REFUSAL: ENVIRONMENT is set to 'production'. Cannot reset in production mode."
        )


def reset_dev_db(yes: bool = False, flush_redis: bool = True) -> dict:
    """Drop schema, run migrations, ensure default workspace, and print counts."""
    if not yes:
        print("REFUSAL: --yes flag is required to perform database reset.", file=sys.stderr)
        sys.exit(2)

    from app.config import get_settings
    settings = get_settings()

    try:
        validate_safety(settings.database_url, settings.environment)
    except ValueError as exc:
        print(f"REFUSAL: {exc}", file=sys.stderr)
        sys.exit(2)

    print(f"Resetting development database: {settings.database_url.split('@')[-1]}")

    # 1. Drop and recreate public schema
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        print("Dropping and recreating public schema...")
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
    engine.dispose()

    # 2. Run migrations
    print("Running migrations...")
    res = subprocess.run([sys.executable, "-m", "scripts.migrate"], cwd=str(backend_dir))
    if res.returncode != 0:
        print("Migration runner failed!", file=sys.stderr)
        sys.exit(res.returncode)

    # 3. Ensure default workspace
    from app.database import SessionLocal
    from app.services.tenancy import ensure_default_workspace
    from app.models.user import User
    from app.models.workspace import Workspace
    from app.models.notification import Notification
    from sqlalchemy import select, func

    with SessionLocal() as db:
        print("Ensuring global default workspace...")
        ensure_default_workspace(db)

        # 4. Optional Redis flush (only for localhost Redis)
        if flush_redis:
            try:
                from app.services.rate_limit import get_redis_client
                r = get_redis_client()
                redis_url = getattr(settings, "redis_url", "")
                r_parsed = urlparse(redis_url)
                r_host = (r_parsed.hostname or "").lower()
                if r_host in ALLOWED_HOSTS or not r_host:
                    r.flushdb()
                    print("Flushed local Redis database.")
                else:
                    print(f"Skipping Redis flush: host '{r_host}' is not local.")
            except Exception as exc:
                print(f"Warning: Could not flush Redis: {exc}")

        # 5. Query counts
        u_count = db.scalar(select(func.count(User.id))) or 0
        w_count = db.scalar(select(func.count(Workspace.id))) or 0
        n_count = db.scalar(select(func.count(Notification.id))) or 0

    counts_str = f"users {u_count}, workspaces {w_count} (default), notifications {n_count}"
    print(f"counts: {counts_str}")

    return {
        "users": u_count,
        "workspaces": w_count,
        "notifications": n_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Reset local development database and Redis")
    parser.add_argument("--yes", action="store_true", help="Confirm execution of database reset")
    parser.add_argument("--flush-redis", dest="flush_redis", action="store_true", default=True, help="Flush local Redis database (default: True)")
    parser.add_argument("--no-flush-redis", dest="flush_redis", action="store_false", help="Do not flush Redis")

    args = parser.parse_args()
    reset_dev_db(yes=args.yes, flush_redis=args.flush_redis)


if __name__ == "__main__":
    main()
