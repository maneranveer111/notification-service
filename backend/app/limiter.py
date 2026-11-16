from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.services.client_ip import client_ip


def get_api_key(request: Request) -> str:
    """
    Use API key as identifier for rate limiting.
    Falls back to client IP address if no API key present.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key
    return client_ip(request)


settings = get_settings()

limiter = Limiter(
    key_func=get_api_key,
    storage_uri=settings.rate_limit_storage_uri,
    in_memory_fallback_enabled=True,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom response when rate limit is exceeded.
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Try again later.",
            "limit": str(exc.limit.limit),
            "retry_after": "60 seconds",
        },
    )
