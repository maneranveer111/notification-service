"""
Wrapper to run Celery worker as a Render Web Service (free tier).

Render's free tier only exists for Web Services, which require binding
to $PORT. Background Worker services have no free tier. This script
starts the real Celery worker as a subprocess, then runs a minimal
HTTP server just to satisfy Render's port check — it does no real
request handling.
"""

import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


def start_celery():
    subprocess.run(
        [
            "celery",
            "-A", "app.celery_app",
            "worker",
            "--loglevel=info",
            "-Q", "notification_service_queue",
        ]
    )


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