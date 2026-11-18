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
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.config import get_settings

# Module-level reference to the Celery subprocess so the SIGTERM handler can reach it.
_celery_proc = None
# Set to True when a clean shutdown is in progress so start_celery does not
# mistake an intentional Celery exit for a crash and call os._exit(1).
_shutting_down = False
# Set to True only after Popen() succeeds so the health endpoint returns 503
# during the startup window before the subprocess exists.
_worker_ready = False
# Reference to the HTTP health server so the shutdown sequence can stop it
# cleanly from a thread other than the one running serve_forever().
_health_server = None
# Bounded grace period (seconds) to let Celery finish in-flight work before
# forcing termination, so a stuck worker cannot hang the wrapper indefinitely.
_SHUTDOWN_TIMEOUT = 30
# Second bounded wait (seconds) after terminate(); escalate to kill() if the
# process still does not exit within this window.
_KILL_TIMEOUT = 10
# Serializes Celery startup with shutdown so the shutdown thread never observes
# a transient _celery_proc is None while Popen() is in progress, and so a
# SIGTERM that arrives before startup begins can skip launching Celery entirely.
_startup_lock = threading.Lock()


def start_celery():
    global _celery_proc, _worker_ready
    settings = get_settings()
    queue = ",".join(settings.get_queue_names())

    cmd = [
        sys.executable,
        "-m", "celery",
        "-A", "app.celery_app",
        "worker",
        "--loglevel=info",
        "-Q", queue,
        "--pool=solo",
    ]

    if os.environ.get("ENABLE_BEAT") == "true":
        from scripts.scheduler import run_loop
        beat_thread = threading.Thread(target=run_loop, kwargs={"interval": 30}, daemon=True)
        beat_thread.start()

    # Serialize startup with shutdown. If shutdown was requested before we
    # began, skip launching Celery entirely. Holding the lock across Popen()
    # guarantees the shutdown thread cannot observe a transient
    # _celery_proc is None while the subprocess is being created, and that the
    # subprocess — once created — is visible before shutdown finishes.
    with _startup_lock:
        if _shutting_down:
            return
        _celery_proc = subprocess.Popen(cmd)
        _worker_ready = True  # subprocess exists; health checks can now reflect live status
    _celery_proc.wait()
    rc = _celery_proc.returncode

    if _shutting_down:
        # Intentional shutdown (SIGTERM from Render) — exit cleanly so Render
        # does not log this as a crash.
        os._exit(0)

    # Any other exit — including rc == 0 — is unexpected. Force exit code 1
    # so Render detects the stoppage and restarts the service.
    print(
        f"Celery subprocess exited unexpectedly with code {rc}. "
        "Terminating health server so Render restarts the service.",
        flush=True,
    )
    os._exit(1)


def _graceful_shutdown():
    """Complete the graceful shutdown from a dedicated thread.

    Runs outside the signal handler (which executes in the main thread that
    also runs serve_forever), so stopping the HTTP server here cannot deadlock
    with the server loop. The Celery wait is also bounded so a stuck worker
    cannot hang the wrapper indefinitely.
    """
    try:
        # Stop the HTTP health server cleanly. Safe here because this thread is
        # neither the main serve_forever thread nor the Celery worker thread.
        server = _health_server
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass

        # Acquire _startup_lock before reading _celery_proc to close the
        # startup/shutdown race: if Popen() is in progress this blocks until
        # the subprocess reference is committed; if startup has not begun,
        # _shutting_down (already True) prevents start_celery from launching
        # afterward. Send SIGTERM while holding the lock so a just-created
        # process cannot be missed, then release the lock before waiting so
        # the lock is never held across a blocking call.
        with _startup_lock:
            proc = _celery_proc
            if proc is not None:
                try:
                    proc.send_signal(signal.SIGTERM)
                except Exception:
                    pass

        if proc is not None:
            try:
                proc.wait(timeout=_SHUTDOWN_TIMEOUT)
            except subprocess.TimeoutExpired:
                try:
                    proc.terminate()
                except Exception:
                    pass
                # Second bounded wait. If the process still does not exit after
                # terminate(), escalate to kill() and reap it.
                try:
                    proc.wait(timeout=_KILL_TIMEOUT)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        proc.wait()
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass
    finally:
        # Intentional shutdown: exit 0 so Render does not treat this as a crash.
        os._exit(0)


def _handle_sigterm(signum, frame):
    """Initiate a graceful shutdown on Render SIGTERM.

    Runs in the main thread (the same thread running serve_forever), so it must
    not block here or call server.shutdown() directly (that would deadlock the
    HTTP server loop). It marks the shutdown as intentional, forwards SIGTERM
    to the Celery subprocess if it exists, and delegates the bounded wait and
    the HTTP server stop to a dedicated thread.
    """
    global _shutting_down
    _shutting_down = True
    if _celery_proc is not None:
        try:
            _celery_proc.send_signal(signal.SIGTERM)
        except Exception:
            pass
    # Run the rest of the shutdown off the main thread to avoid deadlocking the
    # HTTP server, which runs in the main thread.
    threading.Thread(target=_graceful_shutdown, name="graceful-shutdown").start()


signal.signal(signal.SIGTERM, _handle_sigterm)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 503 until the subprocess has been created.
        # 503 if the subprocess has since exited (crashed or stopped).
        # 200 only while the subprocess is alive.
        alive = _worker_ready and _celery_proc is not None and _celery_proc.poll() is None
        status = 200 if alive else 503
        body = b"Celery worker running" if alive else b"Celery worker not running"
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # silence default HTTP request logging, Celery logs are what matter


if __name__ == "__main__":
    celery_thread = threading.Thread(target=start_celery, daemon=True)
    celery_thread.start()

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    _health_server = server
    print(f"Dummy health server listening on port {port} (Celery running in background)")
    server.serve_forever()