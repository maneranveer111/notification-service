from datetime import datetime, timedelta, timezone
import hashlib
import json
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, Security
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.limiter import limiter
from app.models.delivery_attempt import DeliveryAttempt
from app.models.notification import Notification
from app.models.suppression import Suppression
from app.models.template import Template
from app.models.workspace import Workspace
from app.services.providers import has_email_provider, has_sms_provider, resolve_email_providers
from app.schemas.notification import (
    BatchStatusResponse,
    BulkNotificationCreate,
    BulkNotificationResponse,
    EmailNotificationCreate,
    NotificationQueued,
    NotificationRead,
    SMSNotificationCreate,
    WebhookNotificationCreate,
)
from app.schemas.stats import TimelineItem
from app.security import Principal, get_principal, require_write
from app.services.plans import get_effective_bulk_max
from app.services.quota import consume_quota, release_quota
from app.services.suppression_service import is_suppressed
from app.services.templating import MissingVariables, render
from app.tasks.notification_tasks import (
    enqueue_notification,
    send_email_task,
    send_sms_task,
)

settings = get_settings()

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


def _validate_scheduled_at(scheduled_at: datetime | None, max_days: int) -> None:
    if scheduled_at is None:
        return
    if scheduled_at.tzinfo is None or scheduled_at.tzinfo.utcoffset(scheduled_at) is None:
        raise HTTPException(
            status_code=422,
            detail="scheduled_at must be timezone-aware",
        )
    now = datetime.now(timezone.utc)
    if scheduled_at <= now:
        raise HTTPException(
            status_code=422,
            detail="scheduled_at must be in the future",
        )
    if scheduled_at > now + timedelta(days=max_days):
        raise HTTPException(
            status_code=422,
            detail=f"scheduled_at cannot be more than {max_days} days in the future",
        )


def _queue_notification(
    channel: str,
    recipient: str,
    body: str | None,
    subject: str | None,
    provider: str,
    db: Session,
    response: Response,
    workspace_id: UUID,
    idempotency_key: str | None = None,
    client_id: UUID | None = None,
    template_id: UUID | None = None,
    priority: str = "normal",
    scheduled_at: datetime | None = None,
    batch_id: UUID | None = None,
    category: str = "transactional",
    requested_provider: str | None = None,
) -> NotificationQueued:
    request_hash = None
    scoped_idempotency_key = None

    if idempotency_key:
        if len(idempotency_key) > 200:
            raise HTTPException(
                status_code=422,
                detail="Idempotency-Key header too long (max 200 characters)",
            )
        scoped_idempotency_key = f"{workspace_id}:{idempotency_key}"

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

    # Suppression check (skip for webhook channel)
    if channel != "webhook":
        suppression = is_suppressed(db, workspace_id, channel, recipient, category)
        if suppression:
            notification = Notification(
                workspace_id=workspace_id,
                channel=channel,
                recipient=recipient,
                subject=subject,
                body=body,
                provider=provider,
                requested_provider=requested_provider,
                status="suppressed",
                priority=priority,
                scheduled_at=scheduled_at,
                batch_id=batch_id,
                idempotency_key=scoped_idempotency_key,
                request_hash=request_hash,
                client_id=client_id,
                template_id=template_id,
                category=category,
                error_message=f"Recipient suppressed ({suppression.reason})",
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
            return NotificationQueued(
                id=notification.id,
                status=notification.status,
                channel=notification.channel,
            )

    # Marketing emails require unsubscribe_secret
    if channel == "email" and category == "marketing" and not settings.unsubscribe_secret:
        raise HTTPException(
            status_code=422,
            detail="unsubscribe_secret must be configured to send marketing emails",
        )

    initial_status = "scheduled" if scheduled_at else "pending"

    notification = Notification(
        workspace_id=workspace_id,
        channel=channel,
        recipient=recipient,
        subject=subject,
        body=body,
        provider=provider,
        requested_provider=requested_provider,
        status=initial_status,
        priority=priority,
        scheduled_at=scheduled_at,
        batch_id=batch_id,
        idempotency_key=scoped_idempotency_key,
        request_hash=request_hash,
        client_id=client_id,
        template_id=template_id,
        category=category,
    )
    db.add(notification)

    ws = db.get(Workspace, workspace_id) if workspace_id else None
    if ws:
        consume_quota(ws, 1)

    try:
        db.commit()
        db.refresh(notification)
    except IntegrityError:
        db.rollback()
        if ws:
            release_quota(ws, 1)
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
    except Exception:
        db.rollback()
        if ws:
            release_quota(ws, 1)
        raise

    if not scheduled_at:
        enqueue_notification(notification)

    return NotificationQueued(
        id=notification.id,
        status=notification.status,
        channel=notification.channel,
    )


@router.post("/email", response_model=NotificationQueued, dependencies=[Security(require_write)])
@limiter.limit("10/minute")
def queue_email(
    request: Request,
    response: Response,
    payload: EmailNotificationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    _validate_scheduled_at(payload.scheduled_at, settings.schedule_max_days)

    ws = db.get(Workspace, principal.workspace_id) if principal.workspace_id else None
    if not has_email_provider(db, ws):
        raise HTTPException(
            status_code=422,
            detail={"detail": "No email provider is configured for this workspace", "code": "no_provider"},
        )

    resolved = resolve_email_providers(db, ws)
    if payload.provider:
        if not any(n == payload.provider for n, _ in resolved):
            raise HTTPException(
                status_code=422,
                detail={"detail": "That provider is not configured for this workspace", "code": "provider_not_configured"},
            )
        effective_provider = payload.provider
    elif ws and ws.preferred_email_provider:
        effective_provider = ws.preferred_email_provider
    else:
        effective_provider = "brevo"

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
        if not template or template.workspace_id != principal.workspace_id:
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
        provider=effective_provider,
        requested_provider=payload.provider,
        db=db,
        response=response,
        workspace_id=principal.workspace_id,
        idempotency_key=idempotency_key,
        client_id=principal.client_id,
        template_id=template_id,
        priority=payload.priority,
        scheduled_at=payload.scheduled_at,
        category=payload.category,
    )


@router.post("/sms", response_model=NotificationQueued, dependencies=[Security(require_write)])
@limiter.limit("10/minute")
def queue_sms(
    request: Request,
    response: Response,
    payload: SMSNotificationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    _validate_scheduled_at(payload.scheduled_at, settings.schedule_max_days)

    ws = db.get(Workspace, principal.workspace_id) if principal.workspace_id else None
    if not has_sms_provider(db, ws):
        raise HTTPException(
            status_code=422,
            detail={"detail": "No SMS provider is configured for this workspace", "code": "no_provider"},
        )

    template_id = None
    body = payload.message

    if payload.template_id is not None:
        if payload.message is not None:
            raise HTTPException(
                status_code=422,
                detail="Cannot provide both template_id and message",
            )
        template = db.get(Template, payload.template_id)
        if not template or template.workspace_id != principal.workspace_id:
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
        db=db,
        response=response,
        workspace_id=principal.workspace_id,
        idempotency_key=idempotency_key,
        client_id=principal.client_id,
        template_id=template_id,
        priority=payload.priority,
        scheduled_at=payload.scheduled_at,
        category=payload.category,
    )


@router.post("/webhook", response_model=NotificationQueued, dependencies=[Security(require_write)])
@limiter.limit("10/minute")
def queue_webhook(
    request: Request,
    response: Response,
    payload: WebhookNotificationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    try:
        parsed = urlparse(payload.recipient)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid webhook URL")

    if parsed.scheme != "https":
        raise HTTPException(status_code=422, detail="Webhook URL must use https")

    allowed_hosts = {h.strip() for h in settings.webhook_channel_allowed_hosts.split(",") if h.strip()}
    hostname = parsed.hostname or ""
    if hostname not in allowed_hosts:
        raise HTTPException(
            status_code=422,
            detail=f"Webhook host '{hostname}' is not in the allowed hosts list",
        )

    provider = "slack" if hostname == "hooks.slack.com" else ("discord" if hostname in {"discord.com", "discordapp.com"} else "webhook")

    return _queue_notification(
        channel="webhook",
        recipient=payload.recipient,
        subject=None,
        body=payload.body,
        provider=provider,
        db=db,
        response=response,
        workspace_id=principal.workspace_id,
        idempotency_key=idempotency_key,
        client_id=principal.client_id,
        priority=payload.priority,
        category="transactional",
    )


@router.post("/bulk", response_model=BulkNotificationResponse, dependencies=[Security(require_write)])
@limiter.limit("2/minute")
def bulk_notifications(
    request: Request,
    payload: BulkNotificationCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    ws = db.get(Workspace, principal.workspace_id) if principal.workspace_id else None
    plan_name = getattr(ws, "plan", "free") if ws else "free"
    effective_max = get_effective_bulk_max(plan_name)
    if len(payload.recipients) > effective_max:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": f"Recipient count exceeds maximum of {effective_max}",
                "code": "plan_limit",
                "resource": "bulk_recipients",
                "limit": effective_max,
            },
        )
    if len(payload.recipients) == 0:
        raise HTTPException(
            status_code=422,
            detail="Recipient list cannot be empty",
        )

    _validate_scheduled_at(payload.scheduled_at, settings.schedule_max_days)

    if payload.channel == "email" and not has_email_provider(db, ws):
        raise HTTPException(
            status_code=422,
            detail={"detail": "No email provider is configured for this workspace", "code": "no_provider"},
        )
    elif payload.channel == "sms" and not has_sms_provider(db, ws):
        raise HTTPException(
            status_code=422,
            detail={"detail": "No SMS provider is configured for this workspace", "code": "no_provider"},
        )

    if payload.channel == "email" and payload.category == "marketing" and not settings.unsubscribe_secret:
        raise HTTPException(
            status_code=422,
            detail="unsubscribe_secret must be configured to send marketing emails",
        )

    seen = set()
    unique_recipients = []
    for r in payload.recipients:
        key = r.recipient.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_recipients.append(r)

    template = None
    if payload.template_id is not None:
        if payload.subject is not None or payload.body is not None or payload.message is not None:
            raise HTTPException(
                status_code=422,
                detail="Cannot provide both template_id and direct message fields",
            )
        template = db.get(Template, payload.template_id)
        if not template or template.workspace_id != principal.workspace_id:
            raise HTTPException(status_code=422, detail="Template not found")
        if template.channel != payload.channel:
            raise HTTPException(
                status_code=422,
                detail=f"Template channel '{template.channel}' does not match route channel '{payload.channel}'",
            )
    else:
        if payload.channel == "email":
            if not payload.subject or not payload.body:
                raise HTTPException(
                    status_code=422,
                    detail="Must provide either template_id or both subject and body for email",
                )
        elif payload.channel == "sms":
            if not payload.message:
                raise HTTPException(
                    status_code=422,
                    detail="Must provide either template_id or message for sms",
                )

    if payload.channel == "email":
        resolved = resolve_email_providers(db, ws)
        if getattr(payload, "provider", None):
            if not any(n == payload.provider for n, _ in resolved):
                raise HTTPException(
                    status_code=422,
                    detail={"detail": "That provider is not configured for this workspace", "code": "provider_not_configured"},
                )
            bulk_provider = payload.provider
        elif ws and ws.preferred_email_provider:
            bulk_provider = ws.preferred_email_provider
        else:
            bulk_provider = "brevo"
    else:
        bulk_provider = "twilio"

    requested_provider = payload.provider if payload.channel == "email" else None
    batch_id = uuid4()
    initial_status = "scheduled" if payload.scheduled_at else "pending"
    provider = bulk_provider
    created_notifications = []
    suppressed_count = 0

    for r in unique_recipients:
        if template:
            try:
                if payload.channel == "email":
                    subj = render(template.subject_template or "", r.variables or {}, is_subject=True)
                else:
                    subj = None
                b_text = render(template.body_template, r.variables or {}, is_subject=False)
            except MissingVariables as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"Missing template variables for recipient {r.recipient}: {', '.join(e.names)}",
                )
        else:
            subj = payload.subject if payload.channel == "email" else None
            b_text = payload.body if payload.channel == "email" else payload.message

        suppression = is_suppressed(db, principal.workspace_id, payload.channel, r.recipient, payload.category)
        if suppression:
            suppressed_count += 1
            notif = Notification(
                workspace_id=principal.workspace_id,
                channel=payload.channel,
                recipient=r.recipient,
                subject=subj,
                body=b_text,
                provider=provider,
                requested_provider=requested_provider,
                status="suppressed",
                priority=payload.priority,
                scheduled_at=payload.scheduled_at,
                batch_id=batch_id,
                client_id=principal.client_id,
                template_id=payload.template_id,
                category=payload.category,
                error_message=f"Recipient suppressed ({suppression.reason})",
            )
            db.add(notif)
            created_notifications.append(notif)
            continue

        notif = Notification(
            workspace_id=principal.workspace_id,
            channel=payload.channel,
            recipient=r.recipient,
            subject=subj,
            body=b_text,
            provider=provider,
            requested_provider=requested_provider,
            status=initial_status,
            priority=payload.priority,
            scheduled_at=payload.scheduled_at,
            batch_id=batch_id,
            client_id=principal.client_id,
            template_id=payload.template_id,
            category=payload.category,
        )
        db.add(notif)
        created_notifications.append(notif)

    non_suppressed_count = len(created_notifications) - suppressed_count
    if ws and non_suppressed_count > 0:
        consume_quota(ws, non_suppressed_count)

    try:
        db.commit()
        for n in created_notifications:
            db.refresh(n)
    except Exception:
        db.rollback()
        if ws and non_suppressed_count > 0:
            release_quota(ws, non_suppressed_count)
        raise

    if not payload.scheduled_at:
        for n in created_notifications:
            if n.status != "suppressed":
                enqueue_notification(n)

    queued = len(created_notifications) - suppressed_count
    return BulkNotificationResponse(
        batch_id=batch_id,
        queued=queued,
        suppressed=suppressed_count,
        ids=[n.id for n in created_notifications],
    )


@router.get("/batches/{batch_id}", response_model=BatchStatusResponse)
def get_batch_status(
    batch_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    stmt = (
        select(Notification.status, func.count(Notification.id))
        .where(
            Notification.batch_id == batch_id,
            Notification.workspace_id == principal.workspace_id,
        )
        .group_by(Notification.status)
    )

    rows = db.execute(stmt).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Batch not found")

    counts_by_status = {status: count for status, count in rows}
    total = sum(counts_by_status.values())

    return BatchStatusResponse(
        batch_id=batch_id,
        total=total,
        counts_by_status=counts_by_status,
    )


@router.post("/{notification_id}/cancel", response_model=NotificationRead, dependencies=[Security(require_write)])
def cancel_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    stmt = (
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.status == "scheduled",
            Notification.workspace_id == principal.workspace_id,
        )
        .values(status="cancelled", updated_at=func.now())
    )
    res = db.execute(stmt)
    db.commit()

    if res.rowcount == 0:
        n_stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.workspace_id == principal.workspace_id,
        )
        existing = db.execute(n_stmt).scalar_one_or_none()
        if not existing:
            raise HTTPException(status_code=404, detail="Notification not found")
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel: notification status is '{existing.status}' (must be 'scheduled')",
        )

    return db.get(Notification, notification_id)


@router.get("", response_model=list[NotificationRead])
@limiter.limit("60/minute")
def list_notifications(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    status: str | None = Query(default=None, description="Filter by status (pending/sent/failed/...)"),
    channel: str | None = Query(default=None, description="Filter by channel (email/sms/webhook)"),
    recipient: str | None = Query(default=None, description="Filter by recipient (case-insensitive substring)"),
    provider: str | None = Query(default=None, pattern=r"^[a-z0-9_-]{1,30}$", description="Filter by provider"),
    batch_id: UUID | None = Query(default=None, description="Filter by batch_id"),
    limit: int = Query(default=50, ge=1, le=200, description="Number of records to return"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
):
    filters = [Notification.workspace_id == principal.workspace_id]
    if status:
        filters.append(Notification.status == status)
    if channel:
        filters.append(Notification.channel == channel)
    if batch_id:
        filters.append(Notification.batch_id == batch_id)
    if provider:
        filters.append(Notification.provider == provider)
    if recipient:
        escaped = recipient.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(Notification.recipient.ilike(f"%{escaped}%"))

    count_stmt = select(func.count(Notification.id)).where(*filters)
    base_stmt = select(Notification).where(*filters)

    total_count = db.scalar(count_stmt) or 0
    response.headers["X-Total-Count"] = str(total_count)

    stmt = base_stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
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
    notification = db.get(Notification, notification_id)

    if not notification or notification.workspace_id != principal.workspace_id:
        raise HTTPException(status_code=404, detail="Notification not found")

    return notification


@router.get("/{notification_id}/timeline", response_model=list[TimelineItem])
def get_notification_timeline(
    notification_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    notification = db.get(Notification, notification_id)
    if not notification or notification.workspace_id != principal.workspace_id:
        raise HTTPException(status_code=404, detail="Notification not found")

    attempts = db.scalars(
        select(DeliveryAttempt)
        .where(DeliveryAttempt.notification_id == notification_id)
        .order_by(DeliveryAttempt.attempt_number.asc(), DeliveryAttempt.started_at.asc())
    ).all()
    return list(attempts)


@router.post("/{notification_id}/retry", response_model=NotificationQueued, dependencies=[Security(require_write)])
@limiter.limit("10/minute")
def retry_notification(
    request: Request,
    notification_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    notification = db.get(Notification, notification_id)

    if not notification or notification.workspace_id != principal.workspace_id:
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
            Notification.workspace_id == principal.workspace_id,
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
    enqueue_notification(notification)

    return NotificationQueued(
        id=notification.id,
        status=notification.status,
        channel=notification.channel,
    )
