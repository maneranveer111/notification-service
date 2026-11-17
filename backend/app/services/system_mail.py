import logging

from app.services.email_service import mask_email
from app.tasks.notification_tasks import queue_for
from app.tasks.system_tasks import send_system_email_task

logger = logging.getLogger(__name__)


def queue_system_email(to: str, subject: str, body: str) -> bool:
    """
    Enqueue a system transactional email (verification, reset, invitation).
    Does NOT write to the notifications table.

    Returns True if the Celery task was enqueued successfully, or False if
    enqueueing failed (e.g., broker unavailable). Callers MUST check the return
    value and MUST NOT report a "sent"/"email sent" success when it is False.
    Never raises, to keep the HTTP API contract safe; failures are logged with a
    masked recipient and no credentials or tokens are exposed.
    """
    masked_to = mask_email(to)
    target_queue = queue_for("normal")
    try:
        async_result = send_system_email_task.apply_async(
            args=[to, subject, body],
            queue=target_queue,
        )
        logger.info(
            "Enqueued system email task (task_id=%s, queue=%s, recipient=%s, subject=%r)",
            async_result.id,
            target_queue,
            masked_to,
            subject,
        )
        return True
    except Exception as exc:
        logger.error(
            "Failed to enqueue system email to %s on queue %s: %s",
            masked_to,
            target_queue,
            exc,
            exc_info=True,
        )
        return False

