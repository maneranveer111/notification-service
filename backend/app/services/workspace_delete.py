import logging
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.api_client import ApiClient
from app.models.delivery_attempt import DeliveryAttempt
from app.models.delivery_event import DeliveryEvent
from app.models.invitation import Invitation
from app.models.notification import Notification
from app.models.provider_credential import ProviderCredential
from app.models.suppression import Suppression
from app.models.template import Template
from app.models.user import User
from app.models.workspace import Membership, Workspace

logger = logging.getLogger(__name__)


def delete_workspace(db: Session, workspace_id: UUID) -> int:
    """Delete workspace and all associated data in one transaction.

    Returns the number of notifications deleted.
    Raises ValueError if workspace is not found or is the default workspace.
    Raises any other exception on DB error (caller must handle rollback).
    """
    try:
        # Lock the workspace row so concurrent requests can't race
        ws = db.execute(
            select(Workspace).where(Workspace.id == workspace_id).with_for_update()
        ).scalar_one_or_none()
        if not ws:
            raise ValueError("Workspace not found")
        if ws.slug == "default":
            raise ValueError("Cannot delete default workspace")

        # Count notifications before deleting (for audit log)
        notif_count = db.execute(
            select(func.count(Notification.id)).where(Notification.workspace_id == workspace_id)
        ).scalar() or 0

        # Subquery for notification IDs in this workspace
        notif_ids = select(Notification.id).where(Notification.workspace_id == workspace_id).scalar_subquery()

        # 1. Delete delivery_events belonging to this workspace's notifications
        db.execute(delete(DeliveryEvent).where(DeliveryEvent.notification_id.in_(notif_ids)))

        # 2. Delete delivery_attempts (FK has ondelete=CASCADE from notifications,
        #    but we delete explicitly before notifications to be safe)
        db.execute(delete(DeliveryAttempt).where(DeliveryAttempt.notification_id.in_(notif_ids)))

        # 3. Delete notifications
        db.execute(delete(Notification).where(Notification.workspace_id == workspace_id))

        # 4. Delete templates
        db.execute(delete(Template).where(Template.workspace_id == workspace_id))

        # 5. Delete api_clients (templates referencing client_id already gone)
        db.execute(delete(ApiClient).where(ApiClient.workspace_id == workspace_id))

        # 6. Delete suppressions
        db.execute(delete(Suppression).where(Suppression.workspace_id == workspace_id))

        # 7. Delete provider_credentials (FK has ondelete=CASCADE but explicit is safer)
        db.execute(delete(ProviderCredential).where(ProviderCredential.workspace_id == workspace_id))

        # 8. Delete invitations (FK has ondelete=CASCADE)
        db.execute(delete(Invitation).where(Invitation.workspace_id == workspace_id))

        # 9. Delete memberships (FK has ondelete=CASCADE)
        db.execute(delete(Membership).where(Membership.workspace_id == workspace_id))

        # 10. Clear last_workspace_id on any users pointing here
        db.execute(
            update(User)
            .where(User.last_workspace_id == workspace_id)
            .values(last_workspace_id=None)
        )

        # 11. Delete the workspace row itself
        db.delete(ws)

        db.commit()
        return notif_count

    except Exception:
        db.rollback()
        raise


def cleanup_quota_keys(workspace_id: UUID) -> None:
    """Best-effort Redis quota key cleanup — never raises."""
    try:
        from app.services.rate_limit import get_redis_client  # type: ignore[attr-defined]
        r = get_redis_client()
        keys = r.keys(f"quota:{workspace_id}:*")
        if keys:
            r.delete(*keys)
    except Exception:
        pass


def check_delete_rate_limit(user_id: UUID, limit: int = 5) -> bool:
    """Check rate limit for workspace deletion (5 per hour per user). Fails open."""
    try:
        import time
        from app.services.rate_limit import get_redis_client
        r = get_redis_client()
        unix_hour = int(time.time() // 3600)
        key = f"rl:ws_delete:{user_id}:{unix_hour}"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 3600)
        results = pipe.execute()
        current_count = results[0]
        if current_count > limit:
            return False
        return True
    except Exception as exc:
        logger.warning("Redis rate limit check failed for ws_delete %s: %s", user_id, exc)
        return True

