"""
Signed unsubscribe token helpers.

Token format:  <base64url(payload)>.<base64url(hmac)>
where payload = "<workspace_id>|<channel>|<recipient>" (lowercased recipient)
or legacy: "<channel>|<recipient>".
"""
import base64
import hashlib
import hmac as _hmac
from typing import Any

from app.config import get_settings


class UnsubResult(tuple):
    channel: str
    recipient: str
    workspace_id: str | None

    def __new__(cls, channel: str, recipient: str, workspace_id: str | None = None):
        instance = super().__new__(cls, (channel, recipient))
        instance.channel = channel
        instance.recipient = recipient
        instance.workspace_id = str(workspace_id) if workspace_id else None
        return instance

    def __iter__(self):
        return iter((self.channel, self.recipient))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(payload_b64: str, secret: str) -> str:
    if not secret:
        raise ValueError("UNSUBSCRIBE_SECRET is missing or empty")
    sig = _hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64(sig)


def make_token(channel: str, recipient: str, workspace_id: Any | None = None) -> str:
    settings = get_settings()
    secret = settings.unsubscribe_secret
    if not secret:
        raise ValueError("UNSUBSCRIBE_SECRET is missing or empty")
    if workspace_id:
        payload = f"{workspace_id}|{channel}|{recipient.lower()}"
    else:
        payload = f"{channel}|{recipient.lower()}"
    payload_b64 = _b64(payload.encode())
    sig = _sign(payload_b64, secret)
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> UnsubResult | None:
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

    segments = payload.split("|")
    if len(segments) == 3:
        ws_id, channel, recipient = segments
        if not ws_id or not channel or not recipient:
            return None
        return UnsubResult(channel=channel, recipient=recipient, workspace_id=ws_id)
    elif len(segments) == 2:
        channel, recipient = segments
        if not channel or not recipient:
            return None
        return UnsubResult(channel=channel, recipient=recipient, workspace_id=None)
    return None
