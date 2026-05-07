from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

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

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("/email", response_model=NotificationQueued)
def queue_email(payload: EmailNotificationCreate, db: Session = Depends(get_db)):
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
def queue_sms(payload: SMSNotificationCreate, db: Session = Depends(get_db)):
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

@router.get("/{notification_id}", response_model=NotificationRead)
def get_notification(notification_id: UUID, db: Session = Depends(get_db)):
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

