import logging

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_email(recipient: str, subject: str, body: str) -> str | None:
    """
    Send an email using SendGrid API.

    Returns:
        provider_message_id (str) if successful
        None if failed (raises exception)

    Why we return provider_message_id?
        SendGrid returns a unique message ID in response headers.
        We store it in DB so we can trace the email in SendGrid dashboard later.
    """

    # Step 1: Build the email object
    message = Mail(
        from_email=settings.sendgrid_from_email,
        to_emails=recipient,
        subject=subject,
        plain_text_content=body,
    )

    # Step 2: Send via SendGrid client
    client = SendGridAPIClient(api_key=settings.sendgrid_api_key)
    response = client.send(message)

    # Step 3: Log response
    logger.info(f"SendGrid response status: {response.status_code}")

    # Step 4: Extract message ID from headers
    # SendGrid returns X-Message-Id in response headers
    message_id = response.headers.get("X-Message-Id", None)
    logger.info(f"SendGrid message ID: {message_id}")

    return message_id