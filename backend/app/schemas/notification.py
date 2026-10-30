from uuid import UUID
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, EmailStr, ConfigDict, model_validator


class EmailNotificationCreate(BaseModel):
    recipient: EmailStr
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None)
    template_id: UUID | None = None
    variables: dict[str, str | int | float] | None = None
    priority: Literal["high", "normal", "low"] = "normal"
    scheduled_at: datetime | None = None
    category: Literal["transactional", "marketing"] = "transactional"


class SMSNotificationCreate(BaseModel):
    recipient: str = Field(..., min_length=10, max_length=15)
    message: str | None = Field(default=None, max_length=1600)
    template_id: UUID | None = None
    variables: dict[str, str | int | float] | None = None
    priority: Literal["high", "normal", "low"] = "normal"
    scheduled_at: datetime | None = None
    category: Literal["transactional", "marketing"] = "transactional"


class WebhookNotificationCreate(BaseModel):
    recipient: str  # must be https URL with allowed host
    body: str
    priority: Literal["high", "normal", "low"] = "normal"


class BulkRecipient(BaseModel):
    recipient: str
    variables: dict[str, str | int | float] | None = None


class BulkNotificationCreate(BaseModel):
    channel: Literal["email", "sms"]
    recipients: list[BulkRecipient]
    template_id: UUID | None = None
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None)
    message: str | None = Field(default=None, max_length=1600)
    priority: Literal["high", "normal", "low"] = "normal"
    scheduled_at: datetime | None = None
    category: Literal["transactional", "marketing"] = "transactional"


class BulkNotificationResponse(BaseModel):
    batch_id: UUID
    queued: int
    suppressed: int = 0
    ids: list[UUID]


class BatchStatusResponse(BaseModel):
    batch_id: UUID
    total: int
    counts_by_status: dict[str, int]


class NotificationQueued(BaseModel):
    id: UUID
    status: str
    channel: str

    model_config = ConfigDict(from_attributes=True)


class SuppressionCreate(BaseModel):
    channel: str
    recipient: str
    reason: Literal["opt_out", "bounce"] = "opt_out"


class SuppressionRead(BaseModel):
    id: UUID
    channel: str
    recipient: str
    reason: str
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


def _mask_webhook_recipient(recipient: str) -> str:
    """Return https://<host>/...<last6> for webhook URLs."""
    try:
        parsed = urlparse(recipient)
        host = parsed.netloc or parsed.hostname or ""
        last6 = recipient[-6:] if len(recipient) >= 6 else recipient
        return f"https://{host}/...{last6}"
    except Exception:
        return recipient


class NotificationRead(BaseModel):
    id: UUID
    channel: str
    recipient: str

    subject: str | None = None
    body: str | None = None

    status: str
    priority: str = "normal"
    category: str = "transactional"
    attempt_count: int
    max_attempts: int

    provider: str | None = None
    provider_message_id: str | None = None
    error_message: str | None = None

    delivered_at: datetime | None = None
    sent_at: datetime | None = None
    scheduled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    client_id: UUID | None = None
    template_id: UUID | None = None
    batch_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def mask_webhook_url(self) -> "NotificationRead":
        if self.channel == "webhook":
            object.__setattr__(self, "recipient", _mask_webhook_recipient(self.recipient))
        return self
