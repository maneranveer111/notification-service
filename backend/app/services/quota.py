"""
Quota enforcement and tracking service using Redis with fallback to PostgreSQL.
"""
import calendar
from datetime import datetime, timedelta, timezone
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.api_client import ApiClient
from app.models.invitation import Invitation
from app.models.notification import Notification
from app.models.workspace import Membership, Workspace
from app.services.plans import get_plan
from app.services.rate_limit import get_redis_client

logger = logging.getLogger(__name__)


class QuotaExceeded(Exception):
    def __init__(self, scope: str, limit: int, reset_at: datetime):
        self.scope = scope
        self.limit = limit
        self.reset_at = reset_at
        super().__init__(f"{scope.capitalize()} sending limit reached")

    @property
    def retry_after(self) -> int:
        now = datetime.now(timezone.utc)
        return max(1, int((self.reset_at - now).total_seconds()))

    def to_dict(self) -> dict:
        return {
            "detail": f"{self.scope.capitalize()} sending limit reached",
            "code": "quota_exceeded",
            "scope": self.scope,
            "limit": self.limit,
            "reset_at": self.reset_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


def _get_reset_times(now: datetime) -> tuple[datetime, datetime]:
    """Calculate daily and monthly reset timestamps (UTC)."""
    # Daily resets at next UTC midnight
    next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Monthly resets at 1st of next month midnight UTC
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)

    return next_day, next_month


def consume_quota(workspace: Workspace, n: int) -> None:
    """
    Increment daily and monthly sending counters for the workspace.
    Fails open on Redis errors. If limit is exceeded, rolls back and raises QuotaExceeded.
    """
    settings = get_settings()
    if not settings.quota_enabled or n <= 0:
        return

    plan_name = getattr(workspace, "plan", "free")
    plan = get_plan(plan_name)
    daily_limit = plan.get("daily")
    monthly_limit = plan.get("monthly")

    # If both are None (unlimited), no quota tracking needed
    if daily_limit is None and monthly_limit is None:
        return

    now = datetime.now(timezone.utc)
    key_d = f"quota:{workspace.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{workspace.id}:m:{now.strftime('%Y%m')}"
    reset_d, reset_m = _get_reset_times(now)

    daily_incremented = False
    try:
        r = get_redis_client()
        # 1. Daily limit check
        if daily_limit is not None:
            new_daily = r.incrby(key_d, n)
            daily_incremented = True
            r.expire(key_d, 172800)  # 2 days TTL
            if new_daily > daily_limit:
                r.decrby(key_d, n)
                daily_incremented = False
                raise QuotaExceeded(scope="daily", limit=daily_limit, reset_at=reset_d)

        # 2. Monthly limit check
        if monthly_limit is not None:
            new_monthly = r.incrby(key_m, n)
            r.expire(key_m, 3024000)  # 35 days TTL
            if new_monthly > monthly_limit:
                r.decrby(key_m, n)
                if daily_incremented:
                    r.decrby(key_d, n)
                raise QuotaExceeded(scope="monthly", limit=monthly_limit, reset_at=reset_m)

    except QuotaExceeded:
        raise
    except Exception as exc:
        logger.warning(
            "Redis quota check failed for workspace %s, failing open: %s",
            workspace.id,
            exc,
        )


def release_quota(workspace: Workspace, n: int) -> None:
    """
    Decrement daily and monthly counters on rollback or failure.
    """
    settings = get_settings()
    if not settings.quota_enabled or n <= 0:
        return

    plan_name = getattr(workspace, "plan", "free")
    plan = get_plan(plan_name)
    if plan.get("daily") is None and plan.get("monthly") is None:
        return

    now = datetime.now(timezone.utc)
    key_d = f"quota:{workspace.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{workspace.id}:m:{now.strftime('%Y%m')}"

    try:
        r = get_redis_client()
        if plan.get("daily") is not None:
            val = r.decrby(key_d, n)
            if val < 0:
                r.set(key_d, 0)
        if plan.get("monthly") is not None:
            val = r.decrby(key_m, n)
            if val < 0:
                r.set(key_m, 0)
    except Exception as exc:
        logger.warning("Redis release quota failed for workspace %s: %s", workspace.id, exc)


def get_usage(workspace: Workspace, db: Session) -> dict:
    """
    Get current usage and plan limits for the workspace.
    Tries Redis first, falls back to DB count on error.
    """
    plan_name = getattr(workspace, "plan", "free")
    plan = get_plan(plan_name)
    now = datetime.now(timezone.utc)
    reset_d, reset_m = _get_reset_times(now)

    daily_used = 0
    monthly_used = 0
    key_d = f"quota:{workspace.id}:d:{now.strftime('%Y%m%d')}"
    key_m = f"quota:{workspace.id}:m:{now.strftime('%Y%m')}"

    redis_ok = False
    try:
        r = get_redis_client()
        val_d = r.get(key_d)
        val_m = r.get(key_m)
        daily_used = int(val_d or 0)
        monthly_used = int(val_m or 0)
        redis_ok = True
    except Exception as exc:
        logger.warning("Failed to fetch Redis quota usage, falling back to DB: %s", exc)

    if not redis_ok:
        # DB fallback
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        daily_used = (
            db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.workspace_id == workspace.id,
                    Notification.status != "suppressed",
                    Notification.created_at >= day_start,
                )
            )
            or 0
        )
        monthly_used = (
            db.scalar(
                select(func.count(Notification.id)).where(
                    Notification.workspace_id == workspace.id,
                    Notification.status != "suppressed",
                    Notification.created_at >= month_start,
                )
            )
            or 0
        )

    # API keys count
    api_keys_used = (
        db.scalar(
            select(func.count(ApiClient.id)).where(
                ApiClient.workspace_id == workspace.id,
                ApiClient.is_active == True,
            )
        )
        or 0
    )

    # Members count (active members + pending invitations)
    members_count = (
        db.scalar(
            select(func.count(Membership.user_id)).where(
                Membership.workspace_id == workspace.id
            )
        )
        or 0
    )
    pending_invites_count = (
        db.scalar(
            select(func.count(Invitation.id)).where(
                Invitation.workspace_id == workspace.id,
                Invitation.status == "pending",
            )
        )
        or 0
    )
    total_members_used = members_count + pending_invites_count

    return {
        "plan": plan_name,
        "daily": {
            "used": daily_used,
            "limit": plan.get("daily"),
            "resets_at": reset_d.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "monthly": {
            "used": monthly_used,
            "limit": plan.get("monthly"),
            "resets_at": reset_m.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "api_keys": {
            "used": api_keys_used,
            "limit": plan.get("api_keys"),
        },
        "members": {
            "used": total_members_used,
            "limit": plan.get("members"),
        },
    }

