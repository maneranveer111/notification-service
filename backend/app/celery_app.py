from celery import Celery

from app.config import get_settings

settings = get_settings()

# Create the Celery application
celery = Celery(
    "notification_service",  # name of this Celery app
    broker=settings.redis_url,   # Redis: where jobs WAIT
    backend=settings.redis_url,  # Redis: where results are STORED
    include=["app.tasks.notification_tasks"],  # where our tasks live
)

celery.conf.update(
    # How tasks are serialized when stored in Redis
    task_serializer="json",

    # What formats Celery accepts
    accept_content=["json"],

    # How results are serialized
    result_serializer="json",

    timezone="UTC",
    enable_utc=True,

    # Retry policy: if broker (Redis) is down, retry connecting
    broker_connection_retry_on_startup=True,
)