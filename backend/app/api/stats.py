from datetime import datetime, timedelta, timezone
from typing import Any
import redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.notification import Notification
from app.schemas.stats import (
    StatsOverviewResponse,
    StatsTimeseriesItem,
    TopErrorItem,
)
from app.security import Principal, get_principal

router = APIRouter(prefix="/stats", tags=["Stats"])
settings = get_settings()


def _get_queue_depths() -> dict[str, int]:
    try:
        r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        queues = ["notifications.high", "notifications.default", "notifications.bulk"]
        depths = {}
        for q in queues:
            depths[q] = r.llen(q)
        return depths
    except Exception:
        return {"notifications.high": 0, "notifications.default": 0, "notifications.bulk": 0}


@router.get("/overview", response_model=StatsOverviewResponse)
def get_stats_overview(
    window_hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)

    base_conditions = [
        Notification.created_at >= since,
        Notification.workspace_id == principal.workspace_id,
    ]

    # Status breakdown
    status_rows = db.execute(
        select(Notification.status, func.count(Notification.id))
        .where(*base_conditions)
        .group_by(Notification.status)
    ).all()
    totals_by_status = {row[0]: row[1] for row in status_rows}
    total = sum(totals_by_status.values())

    # Channel breakdown
    channel_rows = db.execute(
        select(Notification.channel, func.count(Notification.id))
        .where(*base_conditions)
        .group_by(Notification.channel)
    ).all()
    by_channel = {row[0]: row[1] for row in channel_rows}

    # Provider breakdown
    provider_rows = db.execute(
        select(Notification.provider, func.count(Notification.id))
        .where(*base_conditions, Notification.provider.is_not(None))
        .group_by(Notification.provider)
    ).all()
    by_provider = {row[0]: row[1] for row in provider_rows}

    # Success rate
    successful = totals_by_status.get("sent", 0) + totals_by_status.get("delivered", 0)
    success_rate = round((successful / total) * 100.0, 2) if total > 0 else 0.0

    # Average attempts
    raw_avg = db.scalar(
        select(func.avg(Notification.attempt_count)).where(*base_conditions)
    )
    avg_attempts = round(float(raw_avg), 2) if raw_avg is not None else 0.0

    # Top errors
    error_conditions = base_conditions + [
        Notification.error_message.is_not(None),
        Notification.status.in_(["failed", "retrying"]),
    ]
    error_rows = db.execute(
        select(Notification.error_message, func.count(Notification.id))
        .where(*error_conditions)
        .group_by(Notification.error_message)
        .order_by(func.count(Notification.id).desc())
        .limit(5)
    ).all()
    top_errors = [TopErrorItem(error=row[0], count=row[1]) for row in error_rows]

    queues = _get_queue_depths() if principal.is_superadmin else {}

    return StatsOverviewResponse(
        window_hours=window_hours,
        total=total,
        totals_by_status=totals_by_status,
        by_channel=by_channel,
        by_provider=by_provider,
        success_rate=success_rate,
        avg_attempts=avg_attempts,
        top_errors=top_errors,
        queues=queues,
    )


@router.get("/timeseries", response_model=list[StatsTimeseriesItem])
def get_stats_timeseries(
    window_hours: int = Query(default=24, ge=1, le=720),
    bucket_hours: int = Query(default=1, ge=1, le=24),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    now = datetime.now(timezone.utc)
    # align to hour
    end_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    start_time = end_time - timedelta(hours=window_hours)

    # Initialize buckets dict
    buckets: dict[datetime, dict[str, int]] = {}
    current = start_time
    while current <= end_time:
        buckets[current] = {"ok": 0, "failed": 0, "other": 0}
        current += timedelta(hours=bucket_hours)

    base_conditions = [
        Notification.created_at >= start_time,
        Notification.created_at <= end_time,
        Notification.workspace_id == principal.workspace_id,
    ]

    # Query grouped by date_trunc
    stmt = (
        select(
            func.date_trunc("hour", Notification.created_at).label("bucket"),
            Notification.status,
            func.count(Notification.id),
        )
        .where(*base_conditions)
        .group_by("bucket", Notification.status)
    )
    rows = db.execute(stmt).all()

    for row in rows:
        raw_bucket = row[0]
        if raw_bucket.tzinfo is None:
            raw_bucket = raw_bucket.replace(tzinfo=timezone.utc)
        status_val = row[1]
        count_val = row[2]

        delta_hours = int((raw_bucket - start_time).total_seconds() // 3600)
        bucket_index = (delta_hours // bucket_hours) * bucket_hours
        aligned_bucket = start_time + timedelta(hours=bucket_index)

        if aligned_bucket in buckets:
            if status_val in ("sent", "delivered"):
                buckets[aligned_bucket]["ok"] += count_val
            elif status_val == "failed":
                buckets[aligned_bucket]["failed"] += count_val
            else:
                buckets[aligned_bucket]["other"] += count_val

    results = []
    for b_time in sorted(buckets.keys()):
        results.append(
            StatsTimeseriesItem(
                bucket=b_time,
                ok=buckets[b_time]["ok"],
                failed=buckets[b_time]["failed"],
                other=buckets[b_time]["other"],
            )
        )
    return results
