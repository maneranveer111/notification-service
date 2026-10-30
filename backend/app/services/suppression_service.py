"""
Suppression check helper shared across API and tasks.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.suppression import Suppression


def is_suppressed(db: Session, channel: str, recipient: str, category: str) -> Suppression | None:
    """
    Returns the Suppression row if this send should be blocked, else None.
    Rules:
    - reason='bounce'  → always blocked (any category)
    - reason='opt_out' → blocked only when category='marketing'
                         transactional messages ignore opt-outs
    """
    recipient_lower = recipient.strip().lower()
    row = db.execute(
        select(Suppression).where(
            Suppression.channel == channel,
            Suppression.recipient == recipient_lower,
        )
    ).scalar_one_or_none()

    if row is None:
        return None
    if row.reason == "bounce":
        return row
    # opt_out: only blocks marketing
    if row.reason == "opt_out" and category == "marketing":
        return row
    return None

