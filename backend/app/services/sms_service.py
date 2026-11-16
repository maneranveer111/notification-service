import ipaddress
import logging
from urllib.parse import urlparse

import requests
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.services.errors import PermanentError, TransientError
from app.services.providers import TwilioConfig, get_platform_sms_provider

logger = logging.getLogger(__name__)


def is_valid_public_callback_url(url: str | None) -> bool:
    """
    Validate that the callback URL uses http or https, has a valid hostname,
    and does not point to localhost, loopback, or unspecified IP addresses.
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme.lower() not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "0.0.0.0"):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback or ip.is_unspecified:
            return False
    except ValueError:
        # Not an IP literal, valid domain name
        pass

    return True


def send_sms(recipient: str, message: str, config: TwilioConfig | None = None) -> str | None:
    """
    Send SMS using Twilio API with provided TwilioConfig or platform credentials.

    Returns:
        provider_message_id (Twilio SID) if successful
    """
    if config is None:
        config = get_platform_sms_provider()

    if config is None:
        raise PermanentError("No SMS provider is configured for this workspace. Connect one in Settings.")

    try:
        # Step 1: Create Twilio client
        client = Client(
            config.account_sid,
            config.auth_token,
        )

        # Step 2: Send SMS
        kwargs = {
            "body": message,
            "from_": config.from_number,
            "to": recipient,
        }
        if config.status_callback and is_valid_public_callback_url(config.status_callback):
            kwargs["status_callback"] = config.status_callback
        elif config.status_callback:
            logger.info(
                "Omitting non-public status_callback URL in local development: %s",
                config.status_callback,
            )

        sms = client.messages.create(**kwargs)

        logger.info(f"Twilio message SID: {sms.sid}")
        return sms.sid

    except TwilioRestException as exc:
        status = getattr(exc, "status", None)
        code = getattr(exc, "code", None)
        msg = f"Twilio error [{code}]: {exc.msg}" if code else f"Twilio error: {getattr(exc, 'msg', str(exc))}"
        if status == 429 or (status is not None and status >= 500):
            raise TransientError(msg) from exc
        else:
            raise PermanentError(msg, failover=False) from exc
    except (requests.exceptions.RequestException, ConnectionError, TimeoutError, OSError) as exc:
        raise TransientError(f"Twilio network error: {exc}") from exc
