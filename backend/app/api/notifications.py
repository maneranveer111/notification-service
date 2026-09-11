from fastapi import Request
from app.limiter import limiter
from app.security import verify_api_key
from fastapi import Security

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, update, func

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
    notification = Notification(
        channel="email",
        recipient=payload.recipient,
        subject=payload.subject,
        body=payload.body,
        provider="brevo",
        status="pending",
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    send_email_task.delay(str(notification.id))

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
    notification = db.get(Notification, notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    return notification


@router.post("/{notification_id}/retry", response_model=NotificationQueued)
@limiter.limit("10/minute")
def retry_notification(request: Request, notification_id: UUID, db: Session = Depends(get_db)):
    # Step 1: Find the notification
    notification = db.get(Notification, notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    MAX_MANUAL_EXTENSIONS = 3
    granted = (notification.max_attempts - 3) 
    if granted >= MAX_MANUAL_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"This notification has already been manually retried {granted} times "
                f"({notification.attempt_count} total attempts). The recipient is "
                "almost certainly permanently invalid -- fix the address/number "
                "and create a new notification instead."
            ),
        )

    result = db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.status == "failed",
        )
        .values(
            status="pending",
            error_message=None,
            provider_message_id=None,
            sent_at=None,

            updated_at=func.now(),

            max_attempts=Notification.max_attempts + 3,
        )
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=409,
            detail="Notification is not retryable: it either does not exist, "
                   "was already claimed by another retry, or is not in 'failed' state.",
        )

    notification = db.get(Notification, notification_id)

    if notification.channel == "email":
        send_email_task.delay(str(notification.id))
    elif notification.channel == "sms":
        send_sms_task.delay(str(notification.id))

    return NotificationQueued(
        id=notification.id,
        status=notification.status,
        channel=notification.channel,
    )
