from fastapi import Request
from app.limiter import limiter
from app.security import verify_api_key
from fastapi import Security

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from uuid import UUID

from app.database import get_db
from app.models.notification import Notification
from app.schemas.notification import (
    EmailNotificationCreate,
    NotificationQueued,
    SMSNotificationCreate,
    NotificationRead,
)
from app.tasks.notification_tasks import send_email_task, send_sms_task

router = APIRouter(prefix="/notifications", 
                   tags=["Notifications"],
                   dependencies=[Security(verify_api_key)],
                )


@router.post("/email", response_model=NotificationQueued)
@limiter.limit("10/minute")
def queue_email(request: Request, payload: EmailNotificationCreate, db: Session = Depends(get_db)):
    # Step 1: Save to DB with status=pending
    notification = Notification(
        channel="email",
        recipient=payload.recipient,
        subject=payload.subject,
        body=payload.body,
        provider="sendgrid",
        status="pending",
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    # Step 2: Queue background task
    send_email_task.delay(str(notification.id))

    # Step 3: Return immediately (don't wait for email to send)
    return NotificationQueued(
        id=notification.id,
        status=notification.status,
        channel=notification.channel,
    )


@router.post("/sms", response_model=NotificationQueued)
@limiter.limit("10/minute")
def queue_sms(request: Request, payload: SMSNotificationCreate, db: Session = Depends(get_db)):
    notification = Notification(
        channel="sms",
        recipient=payload.recipient,
        body=payload.message,
        provider="twilio",
        status="pending",
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    send_sms_task.delay(str(notification.id))

    return NotificationQueued(
        id=notification.id,
        status=notification.status,
        channel=notification.channel,
    )

@router.get("", response_model=list[NotificationRead])
@limiter.limit("60/minute")
def list_notifications(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = Query(default=None, description="Filter by status (pending/sent/failed/...)"),
    channel: str | None = Query(default=None, description="Filter by channel (email/sms)"),
    limit: int = Query(default=50, ge=1, le=200, description="Number of records to return"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
):
    """
    List notifications with optional filters and pagination.

    - limit/offset implement simple pagination
    - ordering newest-first helps see latest activity quickly
    """
    stmt = select(Notification).order_by(Notification.created_at.desc()).offset(offset).limit(limit)

    if status:
        stmt = stmt.where(Notification.status == status)

    if channel:
        stmt = stmt.where(Notification.channel == channel)

    notifications = db.execute(stmt).scalars().all()
    return notifications

@router.get("/{notification_id}", response_model=NotificationRead)
@limiter.limit("60/minute")
def get_notification(request: Request, notification_id: UUID, db: Session = Depends(get_db)):
    """
    Fetch a notification by its ID.
    why this exists:
    - Client apps queue a notification (POST)
    - They get back an id immediately
    - Later they can call this endpoint to check status (pending/sent/failed)
    """
    notification = db.get(Notification, notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return notification


@router.post("/{notification_id}/retry", response_model=NotificationQueued)
@limiter.limit("10/minute")
def retry_notification(request: Request, notification_id: UUID, db: Session = Depends(get_db)):
    """
    Manually retry a failed notification.

    Why this exists:
    - Automatic retries (Celery) happen during task execution
    - But after max_retries is exhausted, status becomes "failed"
    - This endpoint allows manual re-queuing of failed notifications
    - Resets attempt_count and error_message before retrying
    """

    # Step 1: Find the notification
    notification = db.get(Notification, notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    # Step 2: Only allow retry if status is "failed"
    if notification.status not in ["failed", "retrying"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry notification with status '{notification.status}'. Only failed/retrying notifications can be retried."
        )

    # Step 3: Reset notification for fresh retry
    notification.status = "pending"
    notification.attempt_count = 0
    notification.error_message = None
    notification.provider_message_id = None
    notification.sent_at = None
    db.commit()
    db.refresh(notification)

    # Step 4: Re-queue correct task based on channel
    if notification.channel == "email":
        send_email_task.delay(str(notification.id))
    elif notification.channel == "sms":
        send_sms_task.delay(str(notification.id))

    return NotificationQueued(
        id=notification.id,
        status=notification.status,
        channel=notification.channel,
    )