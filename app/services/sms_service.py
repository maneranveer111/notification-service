import logging

from twilio.rest import Client

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_sms(recipient: str, message: str) -> str | None:
    """
    Send SMS using Twilio API.

    Returns:
        provider_message_id (Twilio SID) if successful
    """

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
    )

    logger.info(f"Twilio message SID: {sms.sid}")

    return sms.sid