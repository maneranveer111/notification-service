import hmac
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.database import get_db
from app.models.delivery_event import DeliveryEvent
from app.models.notification import Notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

BREVO_STATUS_MAP = {
    "delivered": "delivered",
    "hard_bounce": "bounced",
    "soft_bounce": "bounced",
    "blocked": "bounced",
    "invalid_email": "bounced",
    "spam": "bounced",
    "error": "bounced",
}

TWILIO_STATUS_MAP = {
    "delivered": "delivered",
    "undelivered": "undelivered",
    "failed": "undelivered",
}


def apply_delivery_event(
    db: Session,
    notification: Notification | None,
    new_status: str | None,
    provider: str,
    event_type: str,
    raw: dict,
    error_detail: str | None = None,
) -> None:
    event = DeliveryEvent(
        id=uuid.uuid4(),
        notification_id=notification.id if notification else None,
        provider=provider,
        event_type=event_type,
        payload=raw,
        received_at=datetime.now(timezone.utc),
    )
    db.add(event)

    if notification is not None:
        if notification.status in {"sent", "processing", "retrying"} and new_status is not None:
            notification.status = new_status
            if new_status == "delivered":
                notification.delivered_at = datetime.now(timezone.utc)
            if error_detail:
                if notification.error_message:
                    notification.error_message = f"{notification.error_message} | {error_detail}"
                else:
                    notification.error_message = error_detail

    db.commit()


@router.post("/brevo")
async def brevo_webhook(
    request: Request,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    settings = get_settings()

    if settings.webhook_verify:
        expected_secret = settings.webhook_secret or ""
        provided_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            provided_token = auth_header[7:].strip()
        elif token:
            provided_token = token

        if not provided_token or not expected_secret or not hmac.compare_digest(provided_token, expected_secret):
            raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event_type = payload.get("event", "unknown")
    raw_message_id = payload.get("message-id") or payload.get("messageId") or payload.get("message_id")

    notification = None
    if raw_message_id:
        raw_val = str(raw_message_id).strip()
        stripped_val = raw_val.strip("<>")
        wrapped_val = f"<{stripped_val}>"
        candidates = [raw_val, stripped_val, wrapped_val]

        stmt = select(Notification).where(Notification.provider_message_id.in_(candidates))
        notification = db.execute(stmt).scalars().first()

    if not notification:
        logger.warning(f"Brevo webhook: no notification found matching message id {raw_message_id}")

    new_status = BREVO_STATUS_MAP.get(str(event_type).lower())
    apply_delivery_event(
        db=db,
        notification=notification,
        new_status=new_status,
        provider="brevo",
        event_type=str(event_type),
        raw=payload,
    )

    return {"status": "ok"}


@router.post("/twilio")
async def twilio_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    try:
        raw_body = await request.body()
        parsed = parse_qs(raw_body.decode("utf-8"))
        form_dict = {k: v[0] for k, v in parsed.items() if v}
    except Exception:
        form_dict = {}

    if settings.webhook_verify:
        signature = request.headers.get("X-Twilio-Signature", "")
        url = f"{settings.public_base_url}/webhooks/twilio"
        validator = RequestValidator(settings.twilio_auth_token or "")
        if not signature or not validator.validate(url, form_dict, signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    message_sid = form_dict.get("MessageSid")
    message_status = form_dict.get("MessageStatus")
    error_code = form_dict.get("ErrorCode")

    notification = None
    if message_sid:
        stmt = select(Notification).where(Notification.provider_message_id == str(message_sid).strip())
        notification = db.execute(stmt).scalars().first()

    if not notification:
        logger.warning(f"Twilio webhook: no notification found matching MessageSid {message_sid}")

    status_key = str(message_status).lower() if message_status else ""
    new_status = TWILIO_STATUS_MAP.get(status_key)

    error_detail = None
    if new_status == "undelivered" and error_code:
        error_detail = f"Twilio error {error_code}"

    apply_delivery_event(
        db=db,
        notification=notification,
        new_status=new_status,
        provider="twilio",
        event_type=str(message_status or "unknown"),
        raw=form_dict,
        error_detail=error_detail,
    )

    return {"status": "ok"}
