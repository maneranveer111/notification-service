"""
Suppression check helper shared across API and tasks.
"""
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.suppression import Suppression


def is_suppressed(
    db: Session,
    workspace_id_or_channel: Any,
    channel_or_recipient: str | None = None,
    recipient_or_category: str | None = None,
    category: str | None = None,
) -> Suppression | None:
    """
    Returns the Suppression row if this send should be blocked, else None.
    Supports:
      is_suppressed(db, workspace_id, channel, recipient, category)
      is_suppressed(db, channel, recipient, category)
    """
    if category is not None:
        workspace_id = workspace_id_or_channel
        channel = channel_or_recipient
        recipient = recipient_or_category
    else:
        workspace_id = None
        channel = workspace_id_or_channel
        recipient = channel_or_recipient
        category = recipient_or_category

    recipient_lower = recipient.strip().lower()
    stmt = select(Suppression).where(
        Suppression.channel == channel,
        Suppression.recipient == recipient_lower,
    )
    if workspace_id is not None:
        stmt = stmt.where(Suppression.workspace_id == workspace_id)

    row = db.execute(stmt).scalars().first()

    if row is None:
        return None
    if row.reason == "bounce":
        return row
    if row.reason == "opt_out" and category == "marketing":
        return row
    return None
