from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.api_client import ApiClient
from app.models.notification import Notification
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.security import Principal, require_admin
from app.services.passwords import hash_password

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    rate_limit_per_minute: int = Field(default=60, ge=1)


class ClientCreatedResponse(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    rate_limit_per_minute: int
    is_active: bool
    created_at: datetime
    api_key: str

    model_config = ConfigDict(from_attributes=True)


class ClientRead(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    rate_limit_per_minute: int
    is_active: bool
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ClientRotateResponse(BaseModel):
    id: UUID
    key_prefix: str
    api_key: str


class ClientRevokeResponse(BaseModel):
    id: UUID
    is_active: bool
    revoked_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ClientUsageResponse(BaseModel):
    client_id: UUID
    total: int
    by_status: dict[str, int]
    last_24_hours: int


def _generate_api_key() -> tuple[str, str, str]:
    """Generates (plaintext_key, key_hash, key_prefix)."""
    raw_key = "nk_live_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


@router.post("/clients", response_model=ClientCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)):
    raw_key, key_hash, key_prefix = _generate_api_key()
    client = ApiClient(
        name=payload.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        is_active=True,
    )
    db.add(client)
    try:
        db.commit()
        db.refresh(client)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Client with name '{payload.name}' already exists.",
        )

    return ClientCreatedResponse(
        id=client.id,
        name=client.name,
        key_prefix=client.key_prefix,
        rate_limit_per_minute=client.rate_limit_per_minute,
        is_active=client.is_active,
        created_at=client.created_at,
        api_key=raw_key,
    )


@router.get("/clients", response_model=list[ClientRead])
def list_clients(db: Session = Depends(get_db)):
    clients = db.execute(select(ApiClient).order_by(ApiClient.created_at.desc())).scalars().all()
    return clients


@router.post("/clients/{id}/rotate", response_model=ClientRotateResponse)
def rotate_client_key(id: UUID, db: Session = Depends(get_db)):
    client = db.get(ApiClient, id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    raw_key, key_hash, key_prefix = _generate_api_key()
    client.key_hash = key_hash
    client.key_prefix = key_prefix
    db.commit()

    return ClientRotateResponse(
        id=client.id,
        key_prefix=client.key_prefix,
        api_key=raw_key,
    )


@router.post("/clients/{id}/revoke", response_model=ClientRevokeResponse)
def revoke_client(id: UUID, db: Session = Depends(get_db)):
    client = db.get(ApiClient, id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.is_active = False
    client.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(client)

    return client


@router.get("/clients/{id}/usage", response_model=ClientUsageResponse)
def get_client_usage(id: UUID, db: Session = Depends(get_db)):
    client = db.get(ApiClient, id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    status_counts_rows = db.execute(
        select(Notification.status, func.count(Notification.id))
        .where(Notification.client_id == id)
        .group_by(Notification.status)
    ).all()

    by_status = {row[0]: row[1] for row in status_counts_rows}
    total = sum(by_status.values())

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    last_24h = db.execute(
        select(func.count(Notification.id)).where(
            Notification.client_id == id,
            Notification.created_at >= since,
        )
    ).scalar() or 0

    return ClientUsageResponse(
        client_id=id,
        total=total,
        by_status=by_status,
        last_24_hours=last_24h,
    )


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return list(users)


@router.patch("/users/{id}", response_model=UserRead)
def update_user(
    id: UUID,
    payload: UserUpdate,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    is_self = principal.user_id is not None and principal.user_id == user.id

    if is_self:
        if payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot deactivate your own account",
            )
        if payload.role is not None and payload.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote your own admin account",
            )

    will_demote_or_deactivate = (
        (payload.is_active is False or (payload.role is not None and payload.role != "admin"))
        and user.role == "admin"
        and user.is_active
    )

    if will_demote_or_deactivate:
        active_admins = db.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.is_active == True)
        ) or 0
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot deactivate or demote the last active admin",
            )

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)

    db.commit()
    db.refresh(user)
    return user


