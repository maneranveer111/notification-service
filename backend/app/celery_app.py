from celery import Celery

from app.config import get_settings

settings = get_settings()

# Create the Celery application
celery = Celery(
    "notification_service",  
    broker=settings.redis_url,  
    backend=settings.redis_url,  
    include=["app.tasks.notification_tasks"],  
)

celery.conf.update(
    task_serializer="json",

    accept_content=["json"],

    result_serializer="json",

    timezone="UTC",
    enable_utc=True,

    broker_connection_retry_on_startup=True,

    task_default_queue="notification_service_queue",

    broker_transport_options={
        "socket_keepalive": True,
        "socket_timeout": 30,
        "socket_connect_timeout": 30,
    },
    redis_backend_transport_options={
        "socket_keepalive": True,
        "socket_timeout": 30,
        "socket_connect_timeout": 30,
    },

    broker_connection_retry=True,
    broker_connection_max_retries=5,
)