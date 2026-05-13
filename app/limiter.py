from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse


def get_api_key(request: Request) -> str:
    """
    Use API key as identifier for rate limiting.
    Falls back to IP address if no API key present.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key
    return get_remote_address(request)


limiter = Limiter(key_func=get_api_key)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom response when rate limit is exceeded.
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Try again later.",
            "limit": str(exc.limit.limit),   # ← fix: access .limit.limit to get readable string
            "retry_after": "60 seconds",
        },
    )