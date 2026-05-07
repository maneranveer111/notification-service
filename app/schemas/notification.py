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

class NotificationRead(BaseModel):
    """
    Response schema for reading notification from the DB.
    why we need this 
    - Controls what fields we return to the client
    - Provides consistent output format
    - Enables FastAPI docs to show exact response structue
    """
    id: UUID
    channel: str
    recipient: str

    subject: str | None = None
    body: str | None = None

    status: str
    attempt_count: int
    max_attempts : int

    provider: str | None = None
    provider_message_id: str | None = None  
    error_message: str | None = None

    sent_at: datetime | None = None
    created_at : datetime
    updated_at: datetime

    model_config = {"from_attributes" : True}
