from uuid import UUID
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, EmailStr, ConfigDict


class EmailNotificationCreate(BaseModel):
    recipient: EmailStr
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None)
    template_id: UUID | None = None
    variables: dict[str, str | int | float] | None = None
    priority: Literal["high", "normal", "low"] = "normal"
    scheduled_at: datetime | None = None


class SMSNotificationCreate(BaseModel):
    recipient: str = Field(..., min_length=10, max_length=15)
    message: str | None = Field(default=None, max_length=1600)
    template_id: UUID | None = None
    variables: dict[str, str | int | float] | None = None
    priority: Literal["high", "normal", "low"] = "normal"
    scheduled_at: datetime | None = None


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


class BulkNotificationResponse(BaseModel):
    batch_id: UUID
    queued: int
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


class NotificationRead(BaseModel):
    id: UUID
    channel: str
    recipient: str

    subject: str | None = None
    body: str | None = None

    status: str
    priority: str = "normal"
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
