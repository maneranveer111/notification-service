"""
Suppression list CRUD endpoints.
POST /suppressions      – any authenticated principal with write access (idempotent)
GET  /suppressions      – admin only (scoped to workspace)
DELETE /suppressions/{id} – admin only (scoped to workspace)
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Security
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.suppression import Suppression
from app.schemas.notification import SuppressionCreate, SuppressionRead
from app.security import Principal, get_principal, require_admin, require_write
from app.services.tenancy import scoped

router = APIRouter(
    prefix="/suppressions",
    tags=["Suppressions"],
    dependencies=[Security(get_principal)],
)


@router.post("", response_model=SuppressionRead, status_code=200, dependencies=[Security(require_write)])
def create_suppression(
    payload: SuppressionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_write),
):
    recipient_lower = payload.recipient.strip().lower()
    stmt = (
        pg_insert(Suppression)
        .values(
            workspace_id=principal.workspace_id,
            channel=payload.channel,
            recipient=recipient_lower,
            reason=payload.reason,
            source="api",
        )
    )
    if payload.reason == "bounce":
        stmt = stmt.on_conflict_do_update(
            constraint="uq_suppressions_workspace_channel_recipient",
            set_=dict(
                reason="bounce",
                source="api",
            ),
            where=(Suppression.reason == "opt_out"),
        ).returning(Suppression)
    else:
        stmt = stmt.on_conflict_do_nothing(
            constraint="uq_suppressions_workspace_channel_recipient"
        ).returning(Suppression)

    result = db.execute(stmt)
    row = result.fetchone()
    db.commit()

    if row:
        return row[0]

    # Already existed – fetch and return
    existing = db.execute(
        select(Suppression).where(
            Suppression.workspace_id == principal.workspace_id,
            Suppression.channel == payload.channel,
            Suppression.recipient == recipient_lower,
        )
    ).scalar_one()
    return existing


@router.get("", response_model=list[SuppressionRead], dependencies=[Security(require_admin)])
def list_suppressions(
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    count_stmt = scoped(select(func.count(Suppression.id)), Suppression, principal)
    total = db.scalar(count_stmt) or 0
    response.headers["X-Total-Count"] = str(total)

    stmt = scoped(select(Suppression), Suppression, principal).order_by(Suppression.created_at.desc()).offset(offset).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return rows


@router.delete("/{suppression_id}", status_code=204, dependencies=[Security(require_admin)])
def delete_suppression(
    suppression_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_admin),
):
    row = db.execute(
        select(Suppression).where(
            Suppression.id == suppression_id,
            Suppression.workspace_id == principal.workspace_id,
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Suppression not found")
    db.delete(row)
    db.commit()
