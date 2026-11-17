"""
Wrapper to run Celery worker as a Render Web Service (free tier).

Render's free tier only exists for Web Services, which require binding
to $PORT. Background Worker services have no free tier. This script
starts the real Celery worker as a subprocess, then runs a minimal
HTTP server just to satisfy Render's port check — it does no real
request handling.
"""

import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.config import get_settings

# Module-level reference to the Celery subprocess so the SIGTERM handler can reach it.
_celery_proc = None


def start_celery():
    global _celery_proc
    settings = get_settings()
    q = settings.celery_queue or "notification_service_queue"
    queue = f"{q}_high,{q},{q}_low"

    cmd = [
        "celery",
        "-A", "app.celery_app",
        "worker",
        "--loglevel=info",
        "-Q", queue,
        "--pool=solo",
    ]

    if os.environ.get("ENABLE_BEAT") == "true":
        cmd.extend(["-B", "--schedule=/tmp/celerybeat-schedule"])

    _celery_proc = subprocess.Popen(cmd)
    _celery_proc.wait()
    rc = _celery_proc.returncode
    print(
        f"Celery subprocess exited with code {rc}. "
        "Terminating health server so Render restarts the service.",
        flush=True,
    )
    os._exit(1)


def _handle_sigterm(signum, frame):
    """Forward SIGTERM to the Celery subprocess so it shuts down cleanly."""
    if _celery_proc is not None:
        _celery_proc.send_signal(signal.SIGTERM)
    sys.exit(0)


signal.signal(signal.SIGTERM, _handle_sigterm)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Celery worker running")

    def log_message(self, format, *args):
        pass  # silence default HTTP request logging, Celery logs are what matter


if __name__ == "__main__":
    celery_thread = threading.Thread(target=start_celery, daemon=True)
    celery_thread.start()

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Dummy health server listening on port {port} (Celery running in background)")
    server.serve_forever()