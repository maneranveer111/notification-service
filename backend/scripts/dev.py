"""
Local development orchestration script.

Starts API, worker, scheduler, and optionally frontend with unified logs
and graceful shutdown.
Usage:
    python -m scripts.dev [--frontend] [--reload] [--check]
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def preflight(check_only: bool = False) -> bool:
    """Check dependencies (Postgres, migrations, Redis) and print settings."""
    from app.config import get_settings
    settings = get_settings()

    print("=== Preflight Checks ===")

    # 1. Postgres reachable
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(settings.database_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
        engine.dispose()
        print("[preflight] Postgres: reachable")
    except Exception as exc:
        print(f"[preflight] Postgres ERROR: Could not connect to database: {exc}", file=sys.stderr)
        return False

    # 2. Migrations at head, applying pending ones via scripts.migrate
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.migration import MigrationContext

        alembic_ini_path = backend_dir / "alembic.ini"
        cfg = Config(str(alembic_ini_path))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)

        temp_engine = create_engine(settings.database_url)
        with temp_engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current_rev = ctx.get_current_revision()
        temp_engine.dispose()

        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()

        if current_rev != head_rev:
            print(f"[preflight] Migrations: pending ({current_rev or 'None'} -> {head_rev}). Applying...")
            res = subprocess.run([sys.executable, "-m", "scripts.migrate"], cwd=str(backend_dir))
            if res.returncode != 0:
                print("[preflight] Migrations ERROR: Migration runner failed", file=sys.stderr)
                return False
            print("[preflight] Migrations: updated to head")
        else:
            print(f"[preflight] Migrations: at head ({head_rev})")
    except Exception as exc:
        print(f"[preflight] Migrations ERROR: {exc}", file=sys.stderr)
        return False

    # 3. Redis reachable
    try:
        from app.services.rate_limit import get_redis_client
        r = get_redis_client()
        if not r.ping():
            print("[preflight] Redis ERROR: ping failed", file=sys.stderr)
            return False
        print("[preflight] Redis: reachable")
    except Exception as exc:
        print(f"[preflight] Redis ERROR: Could not connect to Redis: {exc}", file=sys.stderr)
        return False

    # Effective settings printout
    queue_names_list = settings.get_queue_names()
    print("=== Effective Configuration ===")
    print(f"environment:                 {settings.environment}")
    print(f"signup_mode:                 {settings.signup_mode}")
    print(f"require_email_verification:  {settings.require_email_verification}")
    print(f"system_mail_backend:         {settings.system_mail_backend}")
    print(f"queue_names:                 {','.join(queue_names_list)}")

    if settings.system_mail_backend == "console":
        print("WARNING: system_mail_backend is console: verification links appear in the sign-up page and the worker log")

    print("================================")
    return True


def _stream_output(proc: subprocess.Popen, prefix: str):
    """Read lines from proc.stdout and print with prefix."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            print(f"[{prefix}] {line.rstrip()}", flush=True)
    except Exception:
        pass


def run_dev(with_frontend: bool = False, reload_api: bool = False):
    """Start API, Celery worker, Scheduler, and optionally Frontend."""
    from app.config import get_settings
    settings = get_settings()

    procs: list[tuple[str, subprocess.Popen]] = []

    def _terminate_all():
        print("\nStopping all services...", flush=True)
        for name, p in procs:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        time.sleep(1)
        for name, p in procs:
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass

    # Register signal handlers
    def _sig_handler(signum, frame):
        _terminate_all()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # 1. API: Port 8001 exclusively
    api_cmd = [
        sys.executable,
        "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8001",
    ]
    if reload_api:
        api_cmd.append("--reload")

    api_proc = subprocess.Popen(
        api_cmd,
        cwd=str(backend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    procs.append(("api", api_proc))
    threading.Thread(target=_stream_output, args=(api_proc, "api"), daemon=True).start()

    # 2. Worker
    queue_arg = ",".join(settings.get_queue_names())
    worker_cmd = [
        sys.executable,
        "-m", "celery",
        "-A", "app.celery_app",
        "worker",
        "-Q", queue_arg,
        "--pool=solo",
        "--loglevel=info",
    ]
    worker_proc = subprocess.Popen(
        worker_cmd,
        cwd=str(backend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    procs.append(("worker", worker_proc))
    threading.Thread(target=_stream_output, args=(worker_proc, "worker"), daemon=True).start()

    # 3. Scheduler
    scheduler_cmd = [
        sys.executable,
        "-m", "scripts.scheduler",
    ]
    scheduler_proc = subprocess.Popen(
        scheduler_cmd,
        cwd=str(backend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    procs.append(("scheduler", scheduler_proc))
    threading.Thread(target=_stream_output, args=(scheduler_proc, "scheduler"), daemon=True).start()

    # 4. Optional Frontend
    if with_frontend:
        frontend_dir = backend_dir.parent / "frontend"
        npm_cmd = "npm.cmd" if sys.platform == "win32" and shutil.which("npm.cmd") else "npm"
        web_cmd = [npm_cmd, "run", "dev"]
        try:
            web_proc = subprocess.Popen(
                web_cmd,
                cwd=str(frontend_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            procs.append(("web", web_proc))
            threading.Thread(target=_stream_output, args=(web_proc, "web"), daemon=True).start()
        except Exception as exc:
            print(f"[web] Could not start frontend: {exc}", file=sys.stderr)

    print("All dev services started. Press Ctrl+C to stop.", flush=True)

    try:
        while True:
            time.sleep(1)
            # If any non-web process died unexpectedly, report and exit
            for name, p in procs:
                if p.poll() is not None:
                    print(f"[{name}] exited with code {p.returncode}. Stopping all...", flush=True)
                    _terminate_all()
                    sys.exit(p.returncode or 1)
    except KeyboardInterrupt:
        _terminate_all()
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Local development orchestration")
    parser.add_argument("--frontend", action="store_true", help="Also start frontend (npm run dev)")
    parser.add_argument("--reload", action="store_true", help="Enable reload on API server")
    parser.add_argument("--check", action="store_true", help="Run only preflight checks and exit")

    args = parser.parse_args()

    ready = preflight(check_only=args.check)
    if not ready:
        sys.exit(1)

    if args.check:
        print("Preflight check passed: ready.")
        sys.exit(0)

    run_dev(with_frontend=args.frontend, reload_api=args.reload)


if __name__ == "__main__":
    main()
