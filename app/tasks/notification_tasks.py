import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import Task
from sqlalchemy.orm import Session

from app.celery_app import celery
from app.database import SessionLocal
from app.models.notification import Notification
from app.services.email_service import send_email

# Logger for this module
logger = logging.getLogger(__name__)


class NotificationTask(Task):
    """
    Custom base task class.
    Gives us hooks like on_failure, on_retry, on_success.
    We use this to update DB status automatically.
    """
    abstract = True  # Celery won't register this as a task itself

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Called automatically when task fails all retries.
        exc   = the exception that caused failure
        args  = positional arguments passed to task
        """
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
        """
        Called automatically before each retry.
        """
        notification_id = args[0] if args else None
        if not notification_id:
            return

        logger.warning(f"Retrying task {task_id} for notification {notification_id}: {exc}")

        db: Session = SessionLocal()
        try:
            notification = db.get(Notification, UUID(notification_id))
            if notification:
                notification.status = "retrying"
                notification.attempt_count += 1
                notification.error_message = str(exc)
                db.commit()
        finally:
            db.close()

    def on_success(self, retval, task_id, args, kwargs):
        """
        Called automatically when task succeeds.
        """
        notification_id = args[0] if args else None
        logger.info(f"Task {task_id} succeeded for notification {notification_id}")


@celery.task(
    bind=True,                    # gives access to `self` (the task instance)
    base=NotificationTask,        # use our custom base class
    name="notifications.send_email",
    max_retries=3,                # retry up to 3 times
    default_retry_delay=60,       # wait 60 seconds before retry
)
def send_email_task(self, notification_id: str) -> dict:
    """
    Background task to send an email notification.
    For now: simulates sending (prints log).
    Later: calls SendGrid API.
    """
    logger.info(f"Processing email notification: {notification_id}")

    db: Session = SessionLocal()
    try:
        # Step 1: Get notification from DB
        notification = db.get(Notification, UUID(notification_id))

        if not notification:
            logger.error(f"Notification {notification_id} not found in DB")
            return {"status": "error", "reason": "not found"}

        # Step 2: Update status to "processing"
        notification.status = "processing"
        notification.attempt_count += 1
        db.commit()

        message_id = send_email(
            recipient=notification.recipient,
            subject=notification.subject,
            body=notification.body,
        )

        # Step 4: Mark as sent
        notification.status = "sent"
        notification.sent_at = datetime.now(timezone.utc)
        notification.provider_message_id = message_id
        db.commit()

        logger.info(f"Email sent successfully. Provider message ID. {message_id}")
        logger.info(f"Email notification {notification_id} marked as sent")
        return {"status": "sent", "notification_id": notification_id}

    except Exception as exc:
        db.rollback()
        logger.error(f"Error processing email {notification_id}: {exc}")

        # Step 5: Retry if something goes wrong
        raise self.retry(exc=exc)

    finally:
        db.close()


@celery.task(
    bind=True,
    base=NotificationTask,
    name="notifications.send_sms",
    max_retries=3,
    default_retry_delay=60,
)
def send_sms_task(self, notification_id: str) -> dict:
    """
    Background task to send an SMS notification.
    For now: simulates sending (prints log).
    Later: calls Twilio API.
    """
    logger.info(f"Processing SMS notification: {notification_id}")

    db: Session = SessionLocal()
    try:
        notification = db.get(Notification, UUID(notification_id))

        if not notification:
            logger.error(f"Notification {notification_id} not found in DB")
            return {"status": "error", "reason": "not found"}

        notification.status = "processing"
        notification.attempt_count += 1
        db.commit()

        # Simulate SMS sending
        logger.info(f"[SIMULATED] Sending SMS to {notification.recipient}")
        logger.info(f"Message: {notification.body}")

        notification.status = "sent"
        notification.sent_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"SMS notification {notification_id} marked as sent")
        return {"status": "sent", "notification_id": notification_id}

    except Exception as exc:
        db.rollback()
        logger.error(f"Error processing SMS {notification_id}: {exc}")
        raise self.retry(exc=exc)

    finally:
        db.close()