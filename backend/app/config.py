from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # points to project root (notification-service/)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "Notification Service"
    debug: bool = False

    database_url: str
    redis_url: str = "redis://localhost:6379"

    db_pool_size: int = 5        
    db_max_overflow: int = 5     
    db_pool_timeout: int = 30    
    db_pool_recycle: int = 1800  
    celery_queue: str = "notification_service_queue"

    public_base_url: str = "http://localhost:8001"
    webhook_secret: str | None = None
    webhook_verify: bool = True

    email_provider_order: str = "brevo,smtp"
    smtp_host: str | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_port: int = 587
    smtp_use_tls: bool = True
    
    brevo_api_key: str | None = None
    brevo_from_email: str | None = None

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None

    api_key: str

    frontend_url: str = "http://localhost:5173"

    schedule_max_days: int = 30
    bulk_max_recipients: int = 200


@lru_cache
def get_settings() -> Settings:
    # Cached: first call creates Settings(), later calls reuse same object
    return Settings()
