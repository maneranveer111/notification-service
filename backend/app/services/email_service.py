import logging
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

import requests

from app.config import get_settings
from app.services.errors import PermanentError, TransientError

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _send_brevo(recipient: str, subject: str, body: str) -> str | None:
    settings = get_settings()
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

    try:
        response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=10)
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise TransientError(f"Brevo connection error: {exc}") from exc
    except requests.RequestException as exc:
        raise TransientError(f"Brevo request error: {exc}") from exc

    if response.status_code == 429 or response.status_code >= 500:
        raise TransientError(f"Brevo server/rate-limit error {response.status_code}: {response.text}")
    elif response.status_code in (401, 403):
        raise PermanentError(f"Brevo auth error {response.status_code}: {response.text}", failover=True)
    elif 400 <= response.status_code < 500:
        raise PermanentError(f"Brevo client error {response.status_code}: {response.text}", failover=False)

    try:
        data = response.json()
        message_id = data.get("messageId", None)
        logger.info(f"Brevo message ID: {message_id}")
        return message_id
    except Exception:
        return None


def _send_smtp(recipient: str, subject: str, body: str) -> str | None:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = recipient
    msg_id = make_msgid()
    msg["Message-ID"] = msg_id
    msg.set_content(body)

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        try:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return msg_id
    except smtplib.SMTPAuthenticationError as exc:
        raise PermanentError(f"SMTP auth failure: {exc}", failover=True) from exc
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        raise PermanentError(f"SMTP recipient/sender refused: {exc}", failover=False) from exc
    except smtplib.SMTPResponseException as exc:
        if 400 <= exc.smtp_code < 500:
            raise TransientError(f"SMTP 4xx response: {exc}") from exc
        elif exc.smtp_code == 535:
            raise PermanentError(f"SMTP auth failure: {exc}", failover=True) from exc
        else:
            raise TransientError(f"SMTP error: {exc}") from exc
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, smtplib.SMTPHeloError,
            TimeoutError, OSError, ConnectionError) as exc:
        raise TransientError(f"SMTP connection/timeout error: {exc}") from exc
    except Exception as exc:
        raise TransientError(f"SMTP unexpected error: {exc}") from exc


def _is_provider_configured(provider: str) -> bool:
    settings = get_settings()
    if provider == "brevo":
        return bool(settings.brevo_api_key and settings.brevo_from_email)
    elif provider == "smtp":
        return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from_email)
    return False


def send_email(recipient: str, subject: str, body: str) -> tuple[str, str | None]:
    """
    Send an email iterating configured providers in settings.email_provider_order.
    Fails over across transient errors or failover-enabled permanent errors.

    Returns:
        tuple[provider_name, message_id]
    """
    settings = get_settings()
    raw_order = settings.email_provider_order.split(",")
    providers = [p.strip().lower() for p in raw_order if p.strip()]

    configured_providers = [p for p in providers if _is_provider_configured(p)]
    if not configured_providers:
        raise PermanentError("No email provider configured")

    last_error: Exception | None = None
    for provider in configured_providers:
        try:
            if provider == "brevo":
                msg_id = _send_brevo(recipient, subject, body)
                return ("brevo", msg_id)
            elif provider == "smtp":
                msg_id = _send_smtp(recipient, subject, body)
                return ("smtp", msg_id)
            else:
                logger.warning(f"Unknown email provider: {provider}")
                continue
        except (TransientError, PermanentError) as exc:
            if isinstance(exc, TransientError) or (isinstance(exc, PermanentError) and exc.failover):
                logger.warning(f"Provider '{provider}' failed with {exc}. Failing over to next provider.")
                last_error = exc
                continue
            else:
                raise exc
        except Exception as exc:
            logger.warning(f"Provider '{provider}' failed unexpectedly with {exc}.")
            last_error = TransientError(str(exc))
            continue

    if last_error:
        raise last_error
    raise PermanentError("No email provider configured")