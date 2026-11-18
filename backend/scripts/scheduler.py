"""
Standalone scheduler loop for reliable local execution.

Runs every 30 seconds calling dispatch_scheduled and requeue_stale directly,
writing the beat:last_run Redis heartbeat, logging one line per run,
surviving exceptions, and exiting cleanly on Ctrl+C / SIGINT.
"""

import logging
import os
import signal
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger("scheduler")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [scheduler] %(message)s",
)

_stop_requested = False


def _sig_handler(signum, frame):
    global _stop_requested
    _stop_requested = True
    logger.info("Scheduler received signal %s, shutting down...", signum)


def write_heartbeat():
    """Write beat:last_run heartbeat to Redis with 10-minute expiry."""
    try:
        from app.services.rate_limit import get_redis_client
        r = get_redis_client()
        r.set("beat:last_run", int(time.time()), ex=600)
    except Exception as exc:
        logger.warning("Could not write beat heartbeat to Redis: %s", exc)


def run_once() -> dict:
    """
    Execute one tick of scheduler logic:
    - Calls dispatch_scheduled() directly
    - Calls requeue_stale() directly
    - Writes the beat:last_run Redis heartbeat
    - Logs exactly one summary line
    - Survives exceptions
    """
    write_heartbeat()

    dispatched_info = {}
    requeued_info = {}

    try:
        from app.tasks.notification_tasks import dispatch_scheduled
        dispatched_info = dispatch_scheduled() or {}
    except Exception as exc:
        logger.error("Error in dispatch_scheduled: %s", exc, exc_info=True)

    try:
        from app.tasks.notification_tasks import requeue_stale
        requeued_info = requeue_stale() or {}
    except Exception as exc:
        logger.error("Error in requeue_stale: %s", exc, exc_info=True)

    dispatched_count = (
        dispatched_info.get("dispatched_count", 0)
        or dispatched_info.get("dispatched", 0)
        if isinstance(dispatched_info, dict)
        else 0
    )
    requeued_count = (
        requeued_info.get("requeued_count", 0)
        or requeued_info.get("requeued", 0)
        if isinstance(requeued_info, dict)
        else 0
    )

    logger.info("Scheduler tick: dispatched=%d, requeued=%d", dispatched_count, requeued_count)

    return {
        "dispatched": dispatched_count,
        "requeued": requeued_count,
        "dispatched_count": dispatched_count,
        "requeued_count": requeued_count,
        "timestamp": int(time.time()),
    }


def run_loop(interval: int = 30):
    """Run scheduler loop every `interval` seconds until interrupted."""
    global _stop_requested
    _stop_requested = False

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except (ValueError, AttributeError):
        pass  # Running in non-main thread

    logger.info("Scheduler loop started (interval=%ds)", interval)

    while not _stop_requested:
        start_time = time.time()
        try:
            run_once()
        except Exception as exc:
            logger.error("Unexpected error in scheduler loop: %s", exc, exc_info=True)

        elapsed = time.time() - start_time
        sleep_time = max(0.5, interval - elapsed)

        # Sleep in small increments so shutdown is responsive
        steps = int(sleep_time / 0.5)
        for _ in range(steps):
            if _stop_requested:
                break
            time.sleep(0.5)
        remaining = sleep_time - (steps * 0.5)
        if remaining > 0 and not _stop_requested:
            time.sleep(remaining)

    logger.info("Scheduler loop exited cleanly.")


if __name__ == "__main__":
    try:
        run_loop(30)
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user, exiting.")
        sys.exit(0)
