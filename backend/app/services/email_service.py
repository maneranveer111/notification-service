import logging

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(recipient: str, subject: str, body: str) -> str | None:
    """
    Send an email using Brevo's transactional email API.

    Returns:
        provider_message_id (str) if successful
        None if failed (raises exception)

    """

    payload = {
        "sender": {"email": settings.brevo_from_email},
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": body,
    }

    headers = {
        "accept": "application/json",
        "api-key": settings.brevo_api_key,
        "content-type": "application/json",
    }

    response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=10)
    response.raise_for_status()  

    logger.info(f"Brevo response status: {response.status_code}")

    data = response.json()
    message_id = data.get("messageId", None)
    logger.info(f"Brevo message ID: {message_id}")

    return message_id