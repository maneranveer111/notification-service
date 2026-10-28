import logging
import requests
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import get_settings
from app.services.errors import PermanentError, TransientError

logger = logging.getLogger(__name__)


def send_sms(recipient: str, message: str) -> str | None:
    """
    Send SMS using Twilio API.

    Returns:
        provider_message_id (Twilio SID) if successful
    """
    settings = get_settings()
    try:
        # Step 1: Create Twilio client
        client = Client(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
        )

        # Step 2: Send SMS
        sms = client.messages.create(
            body=message,
            from_=settings.twilio_from_number,  # IMPORTANT: underscore is required
            to=recipient,
            status_callback=f"{settings.public_base_url}/webhooks/twilio",
        )

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