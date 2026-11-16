from celery import Celery
from celery.signals import worker_init

import app.models  # noqa: F401 - ensures all model metadata is registered when Celery loads
from app.config import get_settings
from app.services.startup_checks import validate_production_or_raise

settings = get_settings()


@worker_init.connect
def on_worker_init(**kwargs):
    validate_production_or_raise(settings)


# Create the Celery application
celery = Celery(
    "notification_service",  # name of this Celery app
    broker=settings.redis_url,   # Redis: where jobs WAIT
    backend=settings.redis_url,  # Redis: where results are STORED
    include=["app.tasks.notification_tasks", "app.tasks.system_tasks"],  # where our tasks live
)

celery.conf.update(
    task_serializer="json",

    accept_content=["json"],

    result_serializer="json",

    timezone="UTC",
    enable_utc=True,

    broker_connection_retry_on_startup=True,

    task_default_queue=settings.celery_queue,

    broker_transport_options={
        "socket_keepalive": True,
        "socket_timeout": 30,
        "socket_connect_timeout": 30,
        "queue_order_strategy": "priority",
    },
    redis_backend_transport_options={
        "socket_keepalive": True,
        "socket_timeout": 30,
        "socket_connect_timeout": 30,
    },

    broker_connection_retry=True,
    broker_connection_max_retries=5,

    task_acks_late=True,

    worker_prefetch_multiplier=1,

    beat_schedule={
        "requeue-stale-notifications-every-120-seconds": {
            "task": "notifications.requeue_stale",
            "schedule": 120.0,
        },
        "dispatch-scheduled-notifications-every-30-seconds": {
            "task": "notifications.dispatch_scheduled",
            "schedule": 30.0,
        },
    },
)