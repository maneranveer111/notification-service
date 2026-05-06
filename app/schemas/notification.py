from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, EmailStr


class EmailNotificationCreate(BaseModel):
    recipient: EmailStr                            # validates email format automatically
    subject: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)


class SMSNotificationCreate(BaseModel):
    recipient: str = Field(..., min_length=10, max_length=15)  # phone number
    message: str = Field(..., min_length=1, max_length=1600)


class NotificationQueued(BaseModel):
    id: UUID
    status: str
    channel: str

    class Config:
        from_attributes = True  # allows reading from SQLAlchemy model directly