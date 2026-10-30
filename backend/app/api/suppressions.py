"""
Suppression list CRUD endpoints.
POST /suppressions      – any authenticated principal (idempotent)
GET  /suppressions      – admin only
DELETE /suppressions/{id} – admin only
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.suppression import Suppression
from app.schemas.notification import SuppressionCreate, SuppressionRead
from app.security import Principal, get_principal

router = APIRouter(
    prefix="/suppressions",
    tags=["Suppressions"],
    dependencies=[Security(get_principal)],
)


@router.post("", response_model=SuppressionRead, status_code=200)
def create_suppression(
    payload: SuppressionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if not isinstance(principal, Principal):
        principal = Principal(client_id=None, is_admin=True)

    recipient_lower = payload.recipient.strip().lower()
    stmt = (
        pg_insert(Suppression)
        .values(
            channel=payload.channel,
            recipient=recipient_lower,
            reason=payload.reason,
            source="api",
        )
    )
    if payload.reason == "bounce":
        stmt = stmt.on_conflict_do_update(
            constraint="uq_suppressions_channel_recipient",
            set_=dict(
                reason="bounce",
                source="api",
            ),
            where=(Suppression.reason == "opt_out"),
        ).returning(Suppression)
    else:
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_suppressions_channel_recipient"
        ).returning(Suppression)

    result = db.execute(stmt)
    row = result.fetchone()
    db.commit()

    if row:
        return row[0]

    # Already existed – fetch and return
    existing = db.execute(
        select(Suppression).where(
            Suppression.channel == payload.channel,
            Suppression.recipient == recipient_lower,
        )
    ).scalar_one()
    return existing


@router.get("", response_model=list[SuppressionRead])
def list_suppressions(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if not isinstance(principal, Principal):
        principal = Principal(client_id=None, is_admin=True)
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    rows = db.execute(
        select(Suppression).order_by(Suppression.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return rows


@router.delete("/{suppression_id}", status_code=204)
def delete_suppression(
    suppression_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    if not isinstance(principal, Principal):
        principal = Principal(client_id=None, is_admin=True)
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")

    row = db.get(Suppression, suppression_id)
    if not row:
        raise HTTPException(status_code=404, detail="Suppression not found")
    db.delete(row)
    db.commit()

