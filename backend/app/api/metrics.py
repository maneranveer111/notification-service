import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.notification import Notification

router = APIRouter(tags=["Metrics"])
settings = get_settings()

REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests processed",
    ["method", "handler", "status"],
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "handler"],
    registry=REGISTRY,
)

NOTIFICATIONS_STATUS_GAUGE = Gauge(
    "notifications_total_by_status",
    "Current count of notifications by status and channel",
    ["status", "channel"],
    registry=REGISTRY,
)

# 10s cache for DB scrape
_last_db_scrape_time: float = 0.0
_DB_CACHE_TTL = 10.0


def _update_db_gauges(db: Session) -> None:
    global _last_db_scrape_time
    now_mono = time.monotonic()
    if now_mono - _last_db_scrape_time < _DB_CACHE_TTL:
        return

    try:
        rows = db.execute(
            select(
                Notification.status,
                Notification.channel,
                func.count(Notification.id),
            ).group_by(Notification.status, Notification.channel)
        ).all()

        for row in rows:
            stat, ch, count = row[0], row[1], row[2]
            NOTIFICATIONS_STATUS_GAUGE.labels(status=stat, channel=ch).set(count)

        _last_db_scrape_time = now_mono
    except Exception:
        pass


@router.get("/metrics")
def get_metrics(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    if settings.metrics_token:
        provided_token = None
        if authorization and authorization.startswith("Bearer "):
            provided_token = authorization.split(" ", 1)[1]
        elif token:
            provided_token = token

        if not provided_token or provided_token != settings.metrics_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing metrics token",
            )

    _update_db_gauges(db)
    content = generate_latest(REGISTRY)
    return Response(content=content, media_type=CONTENT_TYPE_LATEST)

