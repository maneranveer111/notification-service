import re
import secrets
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workspace import Workspace

_CACHED_DEFAULT_WORKSPACE_ID: UUID | None = None


def get_default_workspace(db: Session) -> Workspace:
    return ensure_default_workspace(db)


def ensure_default_workspace(db: Session) -> Workspace:
    """
    Global default workspace, idempotent.
    slug='default', is_default=True, use_platform_providers=True, fresh webhook_token.
    """
    ws = db.execute(select(Workspace).where(Workspace.slug == "default")).scalars().first()
    if not ws:
        ws = Workspace(
            name="Default Workspace",
            slug="default",
            is_default=True,
            use_platform_providers=True,
            plan="unlimited",
            webhook_token=secrets.token_urlsafe(32),
        )
        db.add(ws)
        db.commit()
        db.refresh(ws)
    else:
        changed = False
        if not getattr(ws, "is_default", False):
            ws.is_default = True
            changed = True
        if not getattr(ws, "use_platform_providers", False):
            ws.use_platform_providers = True
            changed = True
        if not getattr(ws, "webhook_token", None):
            ws.webhook_token = secrets.token_urlsafe(32)
            changed = True
        if changed:
            db.commit()
            db.refresh(ws)
    return ws


def ensure_personal_default_workspace(db: Session, user) -> Workspace:
    """
    Idempotent: creates the user's private Default workspace
    (slug default-<8 random chars>, is_default true, fresh webhook_token,
    same plan rules as other new workspaces, owner membership) if they have none.
    """
    from app.models.workspace import Membership

    stmt = (
        select(Workspace)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(
            Membership.user_id == user.id,
            Workspace.is_default.is_(True),
            Workspace.slug != "default",
        )
    )
    existing = db.execute(stmt).scalars().first()
    if existing:
        return existing

    random_chars = secrets.token_hex(4)
    slug = f"default-{random_chars}"
    ws = Workspace(
        name="Default",
        slug=slug,
        is_default=True,
        use_platform_providers=False,
        webhook_token=secrets.token_urlsafe(32),
    )
    db.add(ws)
    db.flush()

    mem = Membership(user_id=user.id, workspace_id=ws.id, role="owner")
    db.add(mem)
    db.commit()
    db.refresh(ws)
    return ws



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

