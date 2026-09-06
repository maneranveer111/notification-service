from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

settings = get_settings()

# This tells FastAPI:
# "Look for a header called X-API-Key in every request"
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Dependency that validates the API key.

    Why Security() instead of Depends()?
    - Security() is specifically for authentication dependencies
    - It shows a lock icon in Swagger docs
    - Semantically clearer that this is auth-related

    Why auto_error=False?
    - We handle the error ourselves with a custom message
    - If True, FastAPI returns a generic 403 automatically
    - We want to return 401 (Unauthorized) with a clear message
    """

    # Case 1: Header is missing completely
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is missing. Pass it as X-API-Key header.",
        )

    # Case 2: Header is present but key is wrong
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    # Case 3: Key is correct
    return api_key