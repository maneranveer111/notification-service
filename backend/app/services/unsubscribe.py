"""
Signed unsubscribe token helpers.

Token format:  <base64url(payload)>.<base64url(hmac)>
where payload = "<channel>|<recipient>" (lowercased recipient).
"""
import base64
import hashlib
import hmac as _hmac

from app.config import get_settings


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload_b64: str, secret: str) -> str:
    if not secret:
        raise ValueError("UNSUBSCRIBE_SECRET is missing or empty")
    sig = _hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64(sig)


def make_token(channel: str, recipient: str) -> str:
    settings = get_settings()
    secret = settings.unsubscribe_secret
    if not secret:
        raise ValueError("UNSUBSCRIBE_SECRET is missing or empty")
    payload = f"{channel}|{recipient.lower()}"
    payload_b64 = _b64(payload.encode())
    sig = _sign(payload_b64, secret)
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> tuple[str, str] | None:
    if not token:
        return None
    settings = get_settings()
    secret = settings.unsubscribe_secret
    if not secret:
        return None
    parts = token.split(".")
    if len(parts) != 2:
        return None
    payload_b64, provided_sig = parts[0], parts[1]
    expected_sig = _sign(payload_b64, secret)
    if not _hmac.compare_digest(provided_sig, expected_sig):
        return None
    try:
        padding = 4 - len(payload_b64) % 4
        padded = payload_b64 + "=" * (padding % 4)
        payload = base64.urlsafe_b64decode(padded).decode()
    except Exception:
        return None
    channel, _, recipient = payload.partition("|")
    if not channel or not recipient:
        return None
    return channel, recipient

