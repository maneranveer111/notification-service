import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, Security
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.models.notification import Notification
from app.models.template import Template
from app.schemas.notification import (
    EmailNotificationCreate,
    NotificationQueued,
    NotificationRead,
    SMSNotificationCreate,
)
from app.security import Principal, get_principal
from app.services.templating import MissingVariables, render
from app.tasks.notification_tasks import send_email_task, send_sms_task

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    dependencies=[Security(get_principal)],
)


def _compute_request_hash(channel: str, recipient: str, subject: str | None, body: str | None) -> str:
    payload_dict = {
        "channel": channel,
        "recipient": recipient,
        "subject": subject,
        "body": body,
    }
    payload_json = json.dumps(payload_dict, sort_keys=True)
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _queue_notification(
    channel: str,
    recipient: str,
    body: str | None,
    subject: str | None,
    provider: str,
    task_delay_fn,
    db: Session,
    response: Response,
    idempotency_key: str | None = None,
    client_id: UUID | None = None,
    template_id: UUID | None = None,
) -> NotificationQueued:
    request_hash = None
    scoped_idempotency_key = None

    if idempotency_key:
        if len(idempotency_key) > 200:
            raise HTTPException(
                status_code=422,
                detail="Idempotency-Key header too long (max 200 characters)",
            )
        scoped_idempotency_key = f"{client_id or 'master'}:{idempotency_key}"

        request_hash = _compute_request_hash(
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
        )

        existing = db.execute(
            select(Notification).where(Notification.idempotency_key == scoped_idempotency_key)
        ).scalar_one_or_none()

        if existing:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=422,
                    detail="Idempotency-Key reused with a different request",
                )
            response.headers["Idempotent-Replay"] = "true"
            return NotificationQueued(
                id=existing.id,
                status=existing.status,
                channel=existing.channel,
            )

    notification = Notification(
        channel=channel,
        recipient=recipient,
        subject=subject,
        body=body,
        provider=provider,
        status="pending",
        idempotency_key=scoped_idempotency_key,
        request_hash=request_hash,
        client_id=client_id,
        template_id=template_id,
    )
    db.add(notification)

    try:
        db.commit()
        db.refresh(notification)
    except IntegrityError:
        db.rollback()
        if scoped_idempotency_key:
            existing = db.execute(
                select(Notification).where(Notification.idempotency_key == scoped_idempotency_key)
            ).scalar_one_or_none()
            if existing:
                if existing.request_hash != request_hash:
                    raise HTTPException(
                        status_code=422,
                        detail="Idempotency-Key reused with a different request",
                    )
                response.headers["Idempotent-Replay"] = "true"
                return NotificationQueued(
                    id=existing.id,
                    status=existing.status,
                    channel=existing.channel,
                )
        raise

    task_delay_fn(str(notification.id))

    return NotificationQueued(
        id=notification.id,
        status=notification.status,
        channel=notification.channel,
    )


@router.post("/email", response_model=NotificationQueued)
@limiter.limit("10/minute")
def queue_email(
    request: Request,
    response: Response,
    payload: EmailNotificationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    if not isinstance(principal, Principal):
        principal = Principal(client_id=None, is_admin=True)

    template_id = None
    subject = payload.subject
    body = payload.body

    if payload.template_id is not None:
        if payload.subject is not None or payload.body is not None:
            raise HTTPException(
                status_code=422,
                detail="Cannot provide both template_id and subject/body",
            )
        template = db.get(Template, payload.template_id)
        if not template:
            raise HTTPException(status_code=422, detail="Template not found")
        if not principal.is_admin and template.client_id is not None and template.client_id != principal.client_id:
            raise HTTPException(status_code=422, detail="Template not found")
        if template.channel != "email":
            raise HTTPException(
                status_code=422,
                detail=f"Template channel '{template.channel}' does not match route channel 'email'",
            )
        try:
            subject = render(template.subject_template or "", payload.variables or {}, is_subject=True)
            body = render(template.body_template, payload.variables or {}, is_subject=False)
        except MissingVariables as e:
            raise HTTPException(
                status_code=422,
                detail=f"Missing template variables: {', '.join(e.names)}",
            )
        template_id = template.id
    else:
        if not payload.subject or not payload.body:
            raise HTTPException(
                status_code=422,
                detail="Must provide either template_id or both subject and body",
            )

    return _queue_notification(
        channel="email",
        recipient=payload.recipient,
        subject=subject,
        body=body,
        provider="brevo",
        task_delay_fn=send_email_task.delay,
        db=db,
        response=response,
        idempotency_key=idempotency_key,
        client_id=principal.client_id,
        template_id=template_id,
    )


@router.post("/sms", response_model=NotificationQueued)
@limiter.limit("10/minute")
def queue_sms(
    request: Request,
    response: Response,
    payload: SMSNotificationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    if not isinstance(principal, Principal):
        principal = Principal(client_id=None, is_admin=True)

    template_id = None
    body = payload.message

    if payload.template_id is not None:
        if payload.message is not None:
            raise HTTPException(
                status_code=422,
                detail="Cannot provide both template_id and message",
            )
        template = db.get(Template, payload.template_id)
        if not template:
            raise HTTPException(status_code=422, detail="Template not found")
        if not principal.is_admin and template.client_id is not None and template.client_id != principal.client_id:
            raise HTTPException(status_code=422, detail="Template not found")
        if template.channel != "sms":
            raise HTTPException(
                status_code=422,
                detail=f"Template channel '{template.channel}' does not match route channel 'sms'",
            )
        try:
            body = render(template.body_template, payload.variables or {}, is_subject=False)
        except MissingVariables as e:
            raise HTTPException(
                status_code=422,
                detail=f"Missing template variables: {', '.join(e.names)}",
            )
        template_id = template.id
    else:
        if not payload.message:
            raise HTTPException(
                status_code=422,
                detail="Must provide either template_id or message",
            )

    return _queue_notification(
        channel="sms",
        recipient=payload.recipient,
        subject=None,
        body=body,
        provider="twilio",
        task_delay_fn=send_sms_task.delay,
        db=db,
        response=response,
        idempotency_key=idempotency_key,
        client_id=principal.client_id,
        template_id=template_id,
    )


@router.get("", response_model=list[NotificationRead])
@limiter.limit("60/minute")
def list_notifications(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    status: str | None = Query(default=None, description="Filter by status (pending/sent/failed/...)"),
    channel: str | None = Query(default=None, description="Filter by channel (email/sms)"),
    limit: int = Query(default=50, ge=1, le=200, description="Number of records to return"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
):
    if not isinstance(principal, Principal):
        principal = Principal(client_id=None, is_admin=True)

    stmt = select(Notification).order_by(Notification.created_at.desc()).offset(offset).limit(limit)

    if not principal.is_admin:
        stmt = stmt.where(Notification.client_id == principal.client_id)

    if status:
        stmt = stmt.where(Notification.status == status)

    if channel:
        stmt = stmt.where(Notification.channel == channel)

    notifications = db.execute(stmt).scalars().all()
    return notifications


@router.get("/{notification_id}", response_model=NotificationRead)
@limiter.limit("60/minute")
def get_notification(
    request: Request,
    notification_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if not isinstance(principal, Principal):
        principal = Principal(client_id=None, is_admin=True)

    notification = db.get(Notification, notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not principal.is_admin and notification.client_id != principal.client_id:
        raise HTTPException(status_code=404, detail="Notification not found")

    return notification


@router.post("/{notification_id}/retry", response_model=NotificationQueued)
@limiter.limit("10/minute")
def retry_notification(
    request: Request,
    notification_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if not isinstance(principal, Principal):
        principal = Principal(client_id=None, is_admin=True)

    notification = db.get(Notification, notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not principal.is_admin and notification.client_id != principal.client_id:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notification.status != "failed":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry: notification is not in failed state (currently {notification.status})",
        )

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
