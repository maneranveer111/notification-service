import logging
import random
from datetime import datetime, timezone
from uuid import UUID

from celery import Task
from sqlalchemy.orm import Session

from app.celery_app import celery
from app.database import SessionLocal
from app.models.notification import Notification
from app.services.email_service import send_email
from app.services.sms_service import send_sms
from app.services.errors import PermanentError, TransientError

logger = logging.getLogger(__name__)


class NotificationTask(Task):
    """
    Custom base task class.
    Gives us hooks like on_failure, on_retry, on_success.
    We use this to update DB status automatically.
    """
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        notification_id = args[0] if args else None
        if not notification_id:
            return

        logger.error(f"Task {task_id} failed for notification {notification_id}: {exc}")

        db: Session = SessionLocal()
        try:
            notification = db.get(Notification, UUID(notification_id))
            if notification:
                notification.status = "failed"
                notification.error_message = str(exc)
                db.commit()
        finally:
            db.close()

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        notification_id = args[0] if args else None
        if not notification_id:
            return

        logger.warning(f"Retrying task {task_id} for notification {notification_id}: {exc}")

        db: Session = SessionLocal()
        try:
            notification = db.get(Notification, UUID(notification_id))
            if notification:
                notification.status = "retrying"
                notification.error_message = str(exc)
                db.commit()
        finally:
            db.close()

    def on_success(self, retval, task_id, args, kwargs):
        notification_id = args[0] if args else None
        logger.info(f"Task {task_id} succeeded for notification {notification_id}")


def _deliver(task: Task, notification_id: str, send_fn) -> dict:
    logger.info(f"Processing notification: {notification_id}")
    db: Session = SessionLocal()
    try:
        notification = db.get(Notification, UUID(notification_id))
        if not notification:
            logger.error(f"Notification {notification_id} not found in DB")
            return {"status": "error", "reason": "not found"}

        # Guard against acks_late redelivery double-sends
        if notification.status in ("sent", "delivered"):
            logger.info(f"Notification {notification_id} already {notification.status}, skipping")
            return {"status": "skipped"}

        # Set processing, increment attempt_count
        notification.status = "processing"
        notification.attempt_count += 1
        db.commit()

        try:
            res = send_fn(notification)
            if isinstance(res, tuple):
                provider_name, message_id = res
            else:
                provider_name = notification.provider or ("twilio" if notification.channel == "sms" else "brevo")
                message_id = res

            notification.status = "sent"
            notification.sent_at = datetime.now(timezone.utc)
            notification.provider_message_id = message_id
            notification.provider = provider_name
            db.commit()

            logger.info(f"Notification {notification_id} sent successfully via {provider_name}")
            return {"status": "sent", "notification_id": notification_id}

        except PermanentError as exc:
            notification.status = "failed"
            notification.error_message = str(exc)
            db.commit()
            logger.error(f"Permanent error delivering notification {notification_id}: {exc}")
            return {"status": "failed", "notification_id": notification_id, "reason": str(exc)}
        except Exception as exc:
            db.rollback()
            logger.warning(f"Error delivering notification {notification_id}: {exc}")
            retries = getattr(task.request, "retries", 0)
            countdown = min(600, 30 * (2 ** retries)) + random.randint(0, 10)
            raise task.retry(exc=exc, countdown=countdown)

    finally:
        db.close()


@celery.task(
    bind=True,
    base=NotificationTask,
    name="notifications.send_email",
    max_retries=3,
)
def send_email_task(self, notification_id: str) -> dict:
    return _deliver(
        self,
        notification_id,
        lambda n: send_email(
            recipient=n.recipient,
            subject=n.subject or "",
            body=n.body or "",
        ),
    )


@celery.task(
    bind=True,
    base=NotificationTask,
    name="notifications.send_sms",
    max_retries=3,
)
def send_sms_task(self, notification_id: str) -> dict:
    return _deliver(
        self,
        notification_id,
        lambda n: ("twilio", send_sms(
            recipient=n.recipient,
            message=n.body or "",
        )),
    )