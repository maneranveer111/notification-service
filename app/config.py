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

    sendgrid_api_key: str | None = None
    sendgrid_from_email: str | None = None

    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None


@lru_cache
def get_settings() -> Settings:
    # Cached: first call creates Settings(), later calls reuse same object
    return Settings()