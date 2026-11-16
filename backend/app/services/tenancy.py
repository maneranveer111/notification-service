import re
import secrets
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workspace import Workspace

_CACHED_DEFAULT_WORKSPACE_ID: UUID | None = None


def get_default_workspace(db: Session) -> Workspace:
    global _CACHED_DEFAULT_WORKSPACE_ID
    if _CACHED_DEFAULT_WORKSPACE_ID is not None:
        ws = db.get(Workspace, _CACHED_DEFAULT_WORKSPACE_ID)
        if ws:
            return ws
    ws = db.execute(select(Workspace).where(Workspace.slug == "default")).scalar_one_or_none()
    if not ws:
        # Fallback if first workspace or during bootstrap
        ws = db.execute(select(Workspace).order_by(Workspace.created_at.asc())).scalar_one_or_none()
    if ws:
        _CACHED_DEFAULT_WORKSPACE_ID = ws.id
        return ws
    raise RuntimeError("Default workspace not found")


def get_default_workspace_id(db: Session) -> UUID:
    return get_default_workspace(db).id


def scoped(stmt, model, principal):
    """
    Apply tenant scoping to any select/update/delete statement.
    """
    if hasattr(principal, "workspace_id") and principal.workspace_id:
        return stmt.where(model.workspace_id == principal.workspace_id)
    return stmt


def generate_workspace_slug(name: str) -> str:
    """
    Generate slug = slugified name + '-' + 4 random lowercase alphanumeric chars.
    """
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not base:
        base = "workspace"
    suffix = secrets.token_hex(2)  # 4 hex chars
    slug = f"{base}-{suffix}"[:60]
    return slug

