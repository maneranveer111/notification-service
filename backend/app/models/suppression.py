import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Suppression(Base):
    __tablename__ = "suppressions"

    __table_args__ = (
        UniqueConstraint("channel", "recipient", name="uq_suppressions_channel_recipient"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)  # stored lowercased
    reason: Mapped[str] = mapped_column(String(20), nullable=False)  # opt_out | bounce
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # api | unsubscribe_link | bounce

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

