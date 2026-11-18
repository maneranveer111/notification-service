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
    environment: str = "development"  # development | production
    debug: bool = False

    database_url: str
    redis_url: str = "redis://localhost:6379"

    db_pool_size: int = 5        
    db_max_overflow: int = 5     
    db_pool_timeout: int = 30    
    db_pool_recycle: int = 1800  
    celery_queue: str = "notification_service_queue"

    def get_queue_names(self) -> list[str]:
        q = self.celery_queue or "notification_service_queue"
        return [f"{q}_high", q, f"{q}_low"]

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
    brevo_from_name: str | None = None

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None

    api_key: str

    jwt_secret: str | None = None
    jwt_expire_minutes: int = 480
    metrics_token: str | None = None
    log_format: str = "text"  # "text" or "json"

    frontend_url: str = "http://localhost:5173"

    schedule_max_days: int = 30
    bulk_max_recipients: int = 200
    max_workspaces_per_user: int = 5
    unsubscribe_secret: str | None = None
    webhook_channel_allowed_hosts: str = "hooks.slack.com,discord.com,discordapp.com"

    signup_mode: str = "open"  # open | invite_only | closed
    require_email_verification: bool = True
    system_mail_backend: str = "provider"  # provider | console
    frontend_public_url: str = "http://localhost:5173"

    # Per-workspace provider credentials & hardening (Tier 4C1)
    encryption_key: str | None = None  # Fernet key(s), comma-separated; first encrypts, all decrypt
    allow_private_smtp_hosts: bool = False  # Set true for self-hosters with internal mail relay
    trusted_proxy_count: int = 0
    rate_limit_storage_uri: str | None = None

    # Plans, Quotas & CAPTCHA (Tier 4C2)
    quota_enabled: bool = True
    turnstile_secret_key: str | None = None
    turnstile_site_key: str | None = None

    @property
    def frontend_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_url.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    # Cached: first call creates Settings(), later calls reuse same object
    return Settings()
