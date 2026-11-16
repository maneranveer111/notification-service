"""
Cloudflare Turnstile CAPTCHA verification service.
"""
import logging
from typing import Optional
from fastapi import HTTPException, Request, status
import requests

from app.config import get_settings
from app.services.client_ip import client_ip

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_captcha(request: Request, captcha_token: Optional[str]) -> None:
    """
    Verify Cloudflare Turnstile CAPTCHA response.
    When settings.turnstile_secret_key is empty/None, CAPTCHA is disabled.
    When enabled:
    - Missing or failed verification raises 400 captcha_failed.
    - Timeout or network failure raises 503 captcha_unavailable (fail closed).
    """
    settings = get_settings()
    secret = settings.turnstile_secret_key
    if not secret:
        return

    if not captcha_token or not captcha_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "CAPTCHA verification failed", "code": "captcha_failed"},
        )

    ip = client_ip(request)
    payload = {
        "secret": secret,
        "response": captcha_token.strip(),
        "remoteip": ip,
    }

    try:
        resp = requests.post(TURNSTILE_VERIFY_URL, data=payload, timeout=5)
        resp_json = resp.json()
        if not resp_json.get("success"):
            logger.info("Turnstile verification rejected: %s", resp_json.get("error-codes"))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": "CAPTCHA verification failed", "code": "captcha_failed"},
            )
    except HTTPException:
        raise
    except requests.RequestException as exc:
        logger.warning("Turnstile verification request error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": "CAPTCHA service unavailable", "code": "captcha_unavailable"},
        )
    except Exception as exc:
        logger.error("Unexpected error in CAPTCHA verification: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"detail": "CAPTCHA service unavailable", "code": "captcha_unavailable"},
        )

