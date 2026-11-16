import hmac
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.database import get_db
from app.models.delivery_event import DeliveryEvent
from app.models.notification import Notification
from app.models.provider_credential import ProviderCredential
from app.models.suppression import Suppression
from app.models.workspace import Workspace
from app.services.crypto import decrypt_json

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

# Brevo event types that trigger a hard-bounce suppression
BREVO_HARD_BOUNCE_EVENTS = {"hard_bounce", "invalid_email", "blocked"}

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def _is_valid_email(email: str | None) -> bool:
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if len(email) < 3 or len(email) > 255 or "@" not in email:
        return False
    return bool(_EMAIL_REGEX.match(email))


def _upsert_suppression(db: Session, channel: str, recipient: str, reason: str, source: str, workspace_id: Any | None = None) -> None:
    """
    Idempotent upsert.
    When a hard bounce arrives for an existing (workspace_id, channel, recipient) with reason='opt_out',
    escalate atomically to reason='bounce' and source='bounce'.
    """
    if not workspace_id:
        from app.services.tenancy import get_default_workspace_id
        workspace_id = get_default_workspace_id(db)

    recipient_lower = recipient.strip().lower()
    stmt = (
        pg_insert(Suppression)
        .values(
            workspace_id=workspace_id,
            channel=channel,
            recipient=recipient_lower,
            reason=reason,
            source=source,
        )
    )
    if reason == "bounce":
        stmt = stmt.on_conflict_do_update(
            constraint="uq_suppressions_workspace_channel_recipient",
            set_=dict(
                reason="bounce",
                source="bounce",
            ),
            where=(Suppression.reason == "opt_out"),
        )
    else:
        stmt = stmt.on_conflict_do_nothing(constraint="uq_suppressions_workspace_channel_recipient")
    db.execute(stmt)


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

    # Auto-suppress on hard bounce for Brevo
    if provider == "brevo" and event_type.lower() in BREVO_HARD_BOUNCE_EVENTS:
        bounce_recipient = None
        if notification is not None and notification.recipient:
            bounce_recipient = notification.recipient
        elif raw and isinstance(raw, dict):
            candidate = raw.get("email")
            if _is_valid_email(candidate):
                bounce_recipient = candidate.strip()

        if bounce_recipient:
            ws_id = getattr(notification, "workspace_id", None)
            _upsert_suppression(
                db=db,
                channel="email",
                recipient=bounce_recipient,
                reason="bounce",
                source="bounce",
                workspace_id=ws_id,
            )

    db.commit()


# ---------------------------------------------------------------------------
# Per-workspace delivery webhooks (Tier 4C1)
# ---------------------------------------------------------------------------

@router.post("/brevo/{token}")
async def brevo_workspace_webhook(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    ws = db.scalar(select(Workspace).where(Workspace.webhook_token == token))
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

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

        stmt = select(Notification).where(
            Notification.workspace_id == ws.id,
            Notification.provider_message_id.in_(candidates),
        )
        notification = db.execute(stmt).scalars().first()

    if not notification:
        logger.warning(
            f"Brevo workspace webhook: no notification found in workspace {ws.id} matching message id {raw_message_id}"
        )

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


@router.post("/twilio/{token}")
async def twilio_workspace_webhook(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    ws = db.scalar(select(Workspace).where(Workspace.webhook_token == token))
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    cred = db.scalar(
        select(ProviderCredential).where(
            ProviderCredential.workspace_id == ws.id,
            ProviderCredential.provider == "twilio",
            ProviderCredential.is_active == True,
        )
    )
    if not cred:
        raise HTTPException(status_code=404, detail="Twilio credentials not configured for workspace")

    try:
        conf = decrypt_json(cred.config_encrypted)
    except Exception:
        raise HTTPException(status_code=404, detail="Twilio credentials unavailable")

    auth_token = conf.get("auth_token", "")
    if not auth_token:
        raise HTTPException(status_code=404, detail="Twilio auth token missing")

    try:
        raw_body = await request.body()
        parsed = parse_qs(raw_body.decode("utf-8"))
        form_dict = {k: v[0] for k, v in parsed.items() if v}
    except Exception:
        form_dict = {}

    if settings.webhook_verify:
        signature = request.headers.get("X-Twilio-Signature", "")
        url = f"{settings.public_base_url}/webhooks/twilio/{token}"
        validator = RequestValidator(auth_token)
        if not signature or not validator.validate(url, form_dict, signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    message_sid = form_dict.get("MessageSid")
    message_status = form_dict.get("MessageStatus")
    error_code = form_dict.get("ErrorCode")

    notification = None
    if message_sid:
        stmt = select(Notification).where(
            Notification.workspace_id == ws.id,
            Notification.provider_message_id == str(message_sid).strip(),
        )
        notification = db.execute(stmt).scalars().first()

    if not notification:
        logger.warning(
            f"Twilio workspace webhook: no notification found in workspace {ws.id} matching MessageSid {message_sid}"
        )

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


# ---------------------------------------------------------------------------
# Platform providers only (legacy routes)
# ---------------------------------------------------------------------------

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
