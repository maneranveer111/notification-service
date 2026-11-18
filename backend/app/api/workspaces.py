import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.workspace import Membership, Workspace
from app.schemas.auth import UserAuthInfo, WorkspaceInfo
from app.security import Principal, get_principal, get_user_principal, require_admin, require_owner
from app.services.jwt_tokens import create_access_token
from app.services.quota import get_usage
from app.services.tenancy import generate_workspace_slug

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Workspaces"])
settings = get_settings()


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class WorkspaceUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class MemberRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(owner|admin|viewer)$")


class SwitchWorkspaceRequest(BaseModel):
    workspace_id: UUID


class TokenSwitchResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    workspace: WorkspaceInfo
    user: UserAuthInfo | None = None
    workspaces: list[WorkspaceInfo] = []
    is_superadmin: bool = False


def _require_admin_role(principal: Principal) -> None:
    if not principal.workspace_role or principal.workspace_role not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")


@router.get("/usage")
def get_workspace_usage(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active workspace")
    ws = db.get(Workspace, principal.workspace_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return get_usage(ws, db)


@router.get("/workspaces", response_model=list[WorkspaceInfo])
def list_workspaces(
    principal: Principal = Depends(get_user_principal),
    db: Session = Depends(get_db),
):
    if not principal.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User authentication required.")
    memberships = db.execute(
        select(Membership).where(Membership.user_id == principal.user_id)
    ).scalars().all()
    result = []
    for m in memberships:
        ws = db.get(Workspace, m.workspace_id)
        if ws:
            result.append(WorkspaceInfo(id=ws.id, name=ws.name, slug=ws.slug, role=m.role))
    return result


@router.post("/workspaces", response_model=WorkspaceInfo, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    principal: Principal = Depends(get_user_principal),
    db: Session = Depends(get_db),
):
    if not principal.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User authentication required.")

    count = db.scalar(
        select(func.count(Membership.user_id)).where(Membership.user_id == principal.user_id)
    ) or 0
    if count >= settings.max_workspaces_per_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Maximum workspace limit ({settings.max_workspaces_per_user}) reached.",
        )

    for _ in range(5):
        slug = generate_workspace_slug(payload.name)
        existing = db.execute(select(Workspace).where(Workspace.slug == slug)).scalar_one_or_none()
        if not existing:
            break
    else:
        slug = generate_workspace_slug(payload.name + "-ws")

    ws = Workspace(name=payload.name, slug=slug, webhook_token=secrets.token_urlsafe(32))
    db.add(ws)
    db.flush()

    membership = Membership(user_id=principal.user_id, workspace_id=ws.id, role="owner")
    db.add(membership)
    db.commit()
    db.refresh(ws)

    return WorkspaceInfo(id=ws.id, name=ws.name, slug=ws.slug, role="owner")


@router.post("/auth/switch-workspace", response_model=TokenSwitchResponse)
def switch_workspace(
    payload: SwitchWorkspaceRequest,
    principal: Principal = Depends(get_user_principal),
    db: Session = Depends(get_db),
):
    if not principal.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User authentication required.")

    membership = db.get(Membership, (principal.user_id, payload.workspace_id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this workspace.")

    ws = db.get(Workspace, payload.workspace_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    user = db.get(User, principal.user_id)
    if user:
        user.last_workspace_id = ws.id
        db.commit()

    # Build the full workspaces list so the frontend can update its switcher
    all_memberships = db.execute(
        select(Membership).where(Membership.user_id == principal.user_id)
    ).scalars().all()
    workspaces_list: list[WorkspaceInfo] = []
    for m in all_memberships:
        wsi = db.get(Workspace, m.workspace_id)
        if wsi:
            workspaces_list.append(WorkspaceInfo(id=wsi.id, name=wsi.name, slug=wsi.slug, role=m.role))

    user_info: UserAuthInfo | None = None
    if user:
        user_info = UserAuthInfo(id=user.id, email=user.email, role=user.role)

    token = create_access_token(
        user_id=principal.user_id,
        email=principal.email,
        role=membership.role,
        workspace_id=ws.id,
    )
    return TokenSwitchResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60,
        workspace=WorkspaceInfo(id=ws.id, name=ws.name, slug=ws.slug, role=membership.role),
        user=user_info,
        workspaces=workspaces_list,
        is_superadmin=user.is_superadmin if user else False,
    )


@router.get("/workspaces/current", response_model=WorkspaceInfo)
def get_current_workspace(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active workspace.")
    ws = db.get(Workspace, principal.workspace_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return WorkspaceInfo(id=ws.id, name=ws.name, slug=ws.slug, role=principal.workspace_role or "")


@router.patch("/workspaces/current", response_model=WorkspaceInfo)
def update_current_workspace(
    payload: WorkspaceUpdate,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_admin_role(principal)
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active workspace.")
    ws = db.get(Workspace, principal.workspace_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    ws.name = payload.name
    db.commit()
    db.refresh(ws)
    return WorkspaceInfo(id=ws.id, name=ws.name, slug=ws.slug, role=principal.workspace_role or "")


@router.get("/workspaces/current/members", response_model=list[dict])
def list_members(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active workspace.")
    memberships = db.execute(
        select(Membership).where(Membership.workspace_id == principal.workspace_id)
    ).scalars().all()
    result = []
    for m in memberships:
        user = db.get(User, m.user_id)
        if user:
            result.append({
                "user_id": str(m.user_id),
                "email": user.email,
                "role": m.role,
            })
    return result


@router.patch("/workspaces/current/members/{user_id}", response_model=dict)
def update_member_role(
    user_id: UUID,
    payload: MemberRoleUpdate,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_admin_role(principal)
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active workspace.")

    if principal.user_id == user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot change your own role.")

    membership = db.get(Membership, (user_id, principal.workspace_id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if membership.role == "owner" and principal.workspace_role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify an owner.")

    if payload.role == "owner" and principal.workspace_role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can grant owner role.")

    if membership.role == "owner" and payload.role != "owner":
        owner_count = db.scalar(
            select(func.count(Membership.user_id)).where(
                Membership.workspace_id == principal.workspace_id,
                Membership.role == "owner",
            )
        ) or 0
        if owner_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot demote the last owner.")

    membership.role = payload.role
    db.commit()
    user = db.get(User, user_id)
    return {"user_id": str(user_id), "email": user.email if user else None, "role": membership.role}


@router.delete("/workspaces/current/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: UUID,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_admin_role(principal)
    if not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active workspace.")

    if principal.user_id == user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot remove yourself.")

    membership = db.get(Membership, (user_id, principal.workspace_id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if membership.role == "owner" and principal.workspace_role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot remove an owner.")

    if membership.role == "owner":
        owner_count = db.scalar(
            select(func.count(Membership.user_id)).where(
                Membership.workspace_id == principal.workspace_id,
                Membership.role == "owner",
            )
        ) or 0
        if owner_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot remove the last owner.")

    db.delete(membership)
    db.commit()


@router.post("/workspaces/current/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_workspace(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if not principal.user_id or not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication required.")

    membership = db.get(Membership, (principal.user_id, principal.workspace_id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not a member of this workspace.")

    if membership.role == "owner":
        owner_count = db.scalar(
            select(func.count(Membership.user_id)).where(
                Membership.workspace_id == principal.workspace_id,
                Membership.role == "owner",
            )
        ) or 0
        if owner_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot leave: you are the last owner.")

    db.delete(membership)
    db.commit()


class DeleteWorkspaceRequest(BaseModel):
    confirm_name: str
    password: str


@router.post("/workspaces/current/delete")
def delete_current_workspace(
    payload: DeleteWorkspaceRequest,
    principal: Principal = Depends(require_owner),
    db: Session = Depends(get_db),
):
    from app.api.accounts import _build_token_response
    from app.services.passwords import verify_password
    from app.services.workspace_delete import check_delete_rate_limit, cleanup_quota_keys, delete_workspace

    if not principal.user_id or not principal.workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication required.")

    if not check_delete_rate_limit(principal.user_id, 5):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
        )

    ws = db.get(Workspace, principal.workspace_id)
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")

    if ws.slug == "default":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The default workspace cannot be deleted.")

    user = db.get(User, principal.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    name_ok = (payload.confirm_name == ws.name)
    pw_ok = verify_password(payload.password, user.password_hash)

    if not name_ok:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Workspace name does not match.")
    if not pw_ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password.")

    workspace_id = principal.workspace_id

    try:
        notif_count = delete_workspace(db, workspace_id)
    except Exception as exc:
        logger.error("Workspace deletion failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete the workspace.",
        )

    try:
        cleanup_quota_keys(workspace_id)
    except Exception:
        pass
    logger.info("Workspace deleted: ws=%s user=%s notifications=%d", workspace_id, principal.user_id, notif_count)

    # Automatically switch the user to their existing Default Workspace
    default_ws = db.execute(select(Workspace).where(Workspace.slug == "default")).scalar_one_or_none()
    next_membership = None
    if default_ws and default_ws.id != workspace_id:
        next_membership = db.get(Membership, (principal.user_id, default_ws.id))

    if not next_membership:
        next_membership = db.execute(
            select(Membership).where(
                Membership.user_id == principal.user_id,
                Membership.workspace_id != workspace_id,
            ).order_by(Membership.created_at.asc())
        ).scalars().first()

    login_body = None
    if next_membership:
        user.last_workspace_id = next_membership.workspace_id
        db.commit()
        db.refresh(user)
        login_body = _build_token_response(user, db, next_membership.workspace_id).model_dump(mode="json")

    return {"deleted": True, "login": login_body}


