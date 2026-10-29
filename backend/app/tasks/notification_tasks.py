import logging
import random
from datetime import datetime, timedelta, timezone
from uuid import UUID

from celery import Task
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.celery_app import celery
from app.config import get_settings
from app.database import SessionLocal
import app.models  # noqa: F401 - ensures all models (Template, ApiClient, etc.) are registered on Base.metadata
from app.models.notification import Notification
from app.services.email_service import send_email
from app.services.sms_service import send_sms
from app.services.errors import PermanentError, TransientError

logger = logging.getLogger(__name__)
settings = get_settings()

STALE_PENDING_MINUTES = 5
STALE_PROCESSING_MINUTES = 15
SWEEPER_BATCH_SIZE = 100


def queue_for(priority: str | None) -> str:
    if priority == "high":
        return f"{settings.celery_queue}_high"
    elif priority == "low":
        return f"{settings.celery_queue}_low"
    return settings.celery_queue


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
        except Exception as db_exc:
            db.rollback()
            logger.error(
                f"Failed to record failure status for notification {notification_id} in on_failure: {db_exc}",
                exc_info=True,
            )
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
        except Exception as db_exc:
            db.rollback()
            logger.error(
                f"Failed to record retry status for notification {notification_id} in on_retry: {db_exc}",
                exc_info=True,
            )
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
            raise task.retry(
                exc=exc,
                countdown=countdown,
                queue=queue_for(notification.priority),
            )
    except Exception:
        db.rollback()
        raise
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


class EnqueueItem:
    def __init__(self, id, channel: str, priority: str = "normal"):
        self.id = id
        self.channel = channel
        self.priority = priority


TASK_BY_CHANNEL = {
    "email": send_email_task,
    "sms": send_sms_task,
}


def enqueue_notification(notification):
    channel = getattr(notification, "channel", None)
    task = TASK_BY_CHANNEL.get(channel)
    if not task:
        return None
    priority = getattr(notification, "priority", "normal")
    queue = queue_for(priority)
    notif_id = getattr(notification, "id", None)
    return task.apply_async(args=[str(notif_id)], queue=queue)


@celery.task(name="notifications.requeue_stale")
def requeue_stale() -> dict:
    """
    Sweeper task running via Celery Beat.
    Re-queues stale pending and processing notifications.
    """
    now = datetime.now(timezone.utc)
    pending_cutoff = now - timedelta(minutes=STALE_PENDING_MINUTES)
    processing_cutoff = now - timedelta(minutes=STALE_PROCESSING_MINUTES)

    db: Session = SessionLocal()
    stale_items = []
    try:
        stmt = (
            select(Notification)
            .where(
                or_(
                    and_(
                        Notification.status == "pending",
                        Notification.updated_at < pending_cutoff,
                    ),
                    and_(
                        Notification.status == "processing",
                        Notification.updated_at < processing_cutoff,
                    ),
                )
            )
            .order_by(Notification.updated_at.asc())
            .limit(SWEEPER_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        stale_notifications = db.execute(stmt).scalars().all()

        for notification in stale_notifications:
            notification.updated_at = datetime.now(timezone.utc)
            stale_items.append(
                EnqueueItem(
                    id=notification.id,
                    channel=notification.channel,
                    priority=notification.priority,
                )
            )

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Error sweeping stale notifications: {exc}")
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()

    for item in stale_items:
        enqueue_notification(item)

    count = len(stale_items)
    logger.info(f"Sweeper requeued {count} stale notification(s)")
    return {"status": "ok", "requeued_count": count}


@celery.task(name="notifications.dispatch_scheduled")
def dispatch_scheduled() -> dict:
    """
    Scheduled sends task running via Celery Beat every 30 seconds.
    Moves due scheduled notifications to pending and enqueues them.
    """
    now = datetime.now(timezone.utc)
    db: Session = SessionLocal()
    dispatched = []
    try:
        stmt = (
            select(Notification)
            .where(
                Notification.status == "scheduled",
                Notification.scheduled_at <= now,
            )
            .order_by(Notification.scheduled_at.asc())
            .limit(200)
            .with_for_update(skip_locked=True)
        )
        notifications = db.execute(stmt).scalars().all()

        for n in notifications:
            n.status = "pending"
            n.updated_at = datetime.now(timezone.utc)
            dispatched.append(
                EnqueueItem(
                    id=n.id,
                    channel=n.channel,
                    priority=n.priority,
                )
            )

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"Error dispatching scheduled notifications: {exc}")
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()

    for item in dispatched:
        enqueue_notification(item)

    count = len(dispatched)
    logger.info(f"Dispatched {count} scheduled notification(s)")
    return {"status": "ok", "dispatched_count": count}