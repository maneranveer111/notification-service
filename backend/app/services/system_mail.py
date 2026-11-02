import logging

from app.tasks.notification_tasks import queue_for
from app.tasks.system_tasks import send_system_email_task

logger = logging.getLogger(__name__)


def queue_system_email(to: str, subject: str, body: str) -> None:
    """
    Enqueue a system transactional email (verification, reset, invitation).
    Does NOT write to the notifications table. Catches enqueue errors and logs a warning.
    """
    try:
        send_system_email_task.apply_async(
            args=[to, subject, body],
            queue=queue_for("normal"),
        )
    except Exception:
        logger.warning("Failed to enqueue system email to %s", to)

