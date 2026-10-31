from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class TimelineItem(BaseModel):
    id: UUID
    attempt_number: int
    provider: str
    started_at: datetime
    duration_ms: int
    outcome: str
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TopErrorItem(BaseModel):
    error: str
    count: int


class StatsOverviewResponse(BaseModel):
    window_hours: int
    total: int
    totals_by_status: dict[str, int]
    by_channel: dict[str, int]
    by_provider: dict[str, int]
    success_rate: float
    avg_attempts: float
    top_errors: list[TopErrorItem]
    queues: dict[str, int] = Field(default_factory=dict)


class StatsTimeseriesItem(BaseModel):
    bucket: datetime
    ok: int
    failed: int
    other: int
