import logging
from urllib.parse import urlparse
from cryptography.fernet import Fernet

from app.config import Settings

logger = logging.getLogger(__name__)

INSECURE_API_KEY_PLACEHOLDERS = {
    "change-me",
    "changeme",
    "your-api-key",
    "ci-test-key",
    "test",
}

VALID_SIGNUP_MODES = {"open", "invite_only", "closed"}


def check_production_settings(settings: Settings) -> tuple[list[str], list[str]]:
    """Validate settings when running in production.

    Only performs validation if settings.environment == 'production'.
    Returns a tuple of (errors, warnings).
    Messages name settings, never their secret values.
    """
    if settings.environment != "production":
        return [], []

    errors: list[str] = []
    warnings: list[str] = []

    # 1. jwt_secret
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        errors.append("jwt_secret must be set and at least 32 characters long")

    # 2. encryption_key
    if not settings.encryption_key:
        errors.append("encryption_key must be set")
    else:
        keys = [k.strip() for k in settings.encryption_key.split(",") if k.strip()]
        if not keys:
            errors.append("encryption_key must contain at least one valid key")
        for key in keys:
            try:
                Fernet(key.encode())
            except Exception:
                errors.append("encryption_key contains an invalid Fernet key")
                break

    # 3. api_key
    if not settings.api_key:
        errors.append("api_key must be set")
    elif len(settings.api_key) < 24:
        errors.append("api_key must be at least 24 characters long")
    elif settings.api_key.strip().lower() in INSECURE_API_KEY_PLACEHOLDERS:
        errors.append("api_key is using an insecure placeholder value")

    # 4. unsubscribe_secret
    if not settings.unsubscribe_secret:
        errors.append("unsubscribe_secret must be set")

    # 5. system_mail_backend
    if settings.system_mail_backend == "console":
        errors.append("system_mail_backend cannot be 'console' in production")

    # 6. public_base_url and frontend_public_url
    def _is_valid_url(url: str | None) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        if parsed.hostname in ("localhost", "127.0.0.1"):
            return True
        return url.startswith("https://")

    if not _is_valid_url(settings.public_base_url):
        errors.append("public_base_url must use https:// in production unless host is localhost")

    if not _is_valid_url(settings.frontend_public_url):
        errors.append("frontend_public_url must use https:// in production unless host is localhost")

    # 7. signup_mode
    if settings.signup_mode not in VALID_SIGNUP_MODES:
        errors.append(f"signup_mode must be one of {', '.join(sorted(VALID_SIGNUP_MODES))}")

    # --- Warnings ---
    # 1. trusted_proxy_count
    if settings.trusted_proxy_count == 0:
        warnings.append("trusted_proxy_count is 0; client IP detection may be inaccurate behind reverse proxies")

    # 2. rate_limit_storage_uri
    if not settings.rate_limit_storage_uri:
        warnings.append("rate_limit_storage_uri is unset; rate limiter will use default storage")

    # 3. metrics_token
    if not settings.metrics_token:
        warnings.append("metrics_token is unset; Prometheus metrics endpoint is unprotected")

    # 4. signup open and turnstile_secret_key unset
    if settings.signup_mode == "open" and not settings.turnstile_secret_key:
        warnings.append("signup_mode is open but turnstile_secret_key is unset; registration has no CAPTCHA protection")

    # 5. log_format
    if settings.log_format != "json":
        warnings.append("log_format is not 'json'; structured JSON logging is recommended in production")

    # 6. celery_queue containing 'dev'
    if "dev" in (settings.celery_queue or "").lower():
        warnings.append("celery_queue contains 'dev'")

    # 7. database_url host is localhost or 127.0.0.1
    db_parsed = urlparse(settings.database_url or "")
    if db_parsed.hostname in ("localhost", "127.0.0.1"):
        warnings.append("database_url host is localhost or 127.0.0.1")

    return errors, warnings


def validate_production_or_raise(settings: Settings) -> None:
    """Run check_production_settings and raise RuntimeError on errors, log warnings."""
    errors, warnings = check_production_settings(settings)
    for warning in warnings:
        logger.warning("Production configuration warning: %s", warning)

    if errors:
        bullet_errors = "\n".join(f"- {err}" for err in errors)
        raise RuntimeError(f"Invalid production configuration:\n{bullet_errors}")
