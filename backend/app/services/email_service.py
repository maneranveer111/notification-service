import logging
import smtplib
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any

import requests

from app.config import get_settings
from app.services.errors import PermanentError, TransientError
from app.services.net_safety import assert_public_host
from app.services.providers import BrevoConfig, SmtpConfig, get_platform_email_providers

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _send_brevo(recipient: str, subject: str, body: str, config: BrevoConfig) -> str | None:
    sender: dict[str, str] = {"email": config.from_email}
    if config.from_name:
        sender["name"] = config.from_name

    payload = {
        "sender": sender,
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": body,
    }

    headers = {
        "accept": "application/json",
        "api-key": config.api_key,
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


def _send_smtp(recipient: str, subject: str, body: str, config: SmtpConfig) -> str | None:
    # SSRF guard at send time for workspace credentials (platform config bypasses)
    if not config.is_platform:
        try:
            assert_public_host(config.host)
        except ValueError as exc:
            raise PermanentError(f"SMTP host safety check failed: {exc}", failover=False) from exc

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.from_email
    msg["To"] = recipient
    msg_id = make_msgid()
    msg["Message-ID"] = msg_id
    msg.set_content(body)

    try:
        server = smtplib.SMTP(config.host, config.port, timeout=10)
        try:
            if config.use_tls:
                server.starttls()
            if config.username and config.password:
                server.login(config.username, config.password)
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
    except PermanentError:
        raise
    except Exception as exc:
        raise TransientError(f"SMTP unexpected error: {exc}") from exc


def _is_provider_configured(provider: str) -> bool:
    settings = get_settings()
    if provider == "brevo":
        return bool(settings.brevo_api_key and settings.brevo_from_email)
    elif provider == "smtp":
        return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_from_email)
    return False


def _build_platform_providers() -> list[tuple[str, Any]]:
    settings = get_settings()
    raw_order = settings.email_provider_order.split(",")
    order = [p.strip().lower() for p in raw_order if p.strip()]

    providers: list[tuple[str, Any]] = []
    for p in order:
        if p == "brevo" and _is_provider_configured("brevo"):
            providers.append(
                (
                    "brevo",
                    BrevoConfig(
                        api_key=settings.brevo_api_key,
                        from_email=settings.brevo_from_email,
                    ),
                )
            )
        elif p == "smtp" and _is_provider_configured("smtp"):
            providers.append(
                (
                    "smtp",
                    SmtpConfig(
                        host=settings.smtp_host,
                        port=settings.smtp_port,
                        username=settings.smtp_user,
                        password=settings.smtp_password,
                        from_email=settings.smtp_from_email,
                        use_tls=settings.smtp_use_tls,
                        is_platform=True,
                    ),
                )
            )
    return providers


def send_email(
    recipient: str,
    subject: str,
    body: str,
    on_attempt: Callable[[str, str, str | None, int, datetime], None] | None = None,
    providers: list[tuple[str, Any]] | None = None,
) -> tuple[str, str | None]:
    """
    Send an email iterating providers in order.
    Fails over across transient errors or failover-enabled permanent errors.

    Returns:
        tuple[provider_name, message_id]
    """
    if providers is None:
        providers = _build_platform_providers()

    if not providers:
        raise PermanentError("No email provider is configured for this workspace. Connect one in Settings.")

    last_error: Exception | None = None
    for provider_name, provider_config in providers:
        attempt_start = time.perf_counter()
        attempted_at = datetime.now(timezone.utc)
        error_msg: str | None = None
        status = "failed"
        message_id: str | None = None

        try:
            if provider_name == "brevo":
                message_id = _send_brevo(recipient, subject, body, provider_config)
            elif provider_name == "smtp":
                message_id = _send_smtp(recipient, subject, body, provider_config)
            else:
                continue

            status = "success"
            return provider_name, message_id

        except TransientError as exc:
            error_msg = str(exc)
            last_error = exc
            http_status = getattr(getattr(exc, 'response', None), 'status_code', None)
            logger.warning("Transient error with provider %s: %s%s. Attempting failover.", provider_name, type(exc).__name__, f" HTTP {http_status}" if http_status else "")
            continue

        except PermanentError as exc:
            error_msg = str(exc)
            last_error = exc
            if exc.failover:
                http_status = getattr(getattr(exc, 'response', None), 'status_code', None)
                logger.warning("Failover-enabled permanent error with %s: %s%s. Failing over.", provider_name, type(exc).__name__, f" HTTP {http_status}" if http_status else "")
                continue
            else:
                http_status = getattr(getattr(exc, 'response', None), 'status_code', None)
                logger.warning("Permanent error with provider %s: %s%s. Aborting.", provider_name, type(exc).__name__, f" HTTP {http_status}" if http_status else "")
                raise

        except Exception as exc:
            error_msg = str(exc)
            last_error = exc
            http_status = getattr(getattr(exc, 'response', None), 'status_code', None)
            logger.warning("Unexpected error with provider %s: %s%s. Attempting failover.", provider_name, type(exc).__name__, f" HTTP {http_status}" if http_status else "")
            continue

        finally:
            attempt_duration_ms = int((time.perf_counter() - attempt_start) * 1000)
            if on_attempt:
                try:
                    on_attempt(provider_name, status, error_msg, attempt_duration_ms, attempted_at)
                except Exception as log_exc:
                    status = getattr(getattr(log_exc, 'response', None), 'status_code', None)
                    logger.warning("Failed to record delivery attempt: %s%s", type(log_exc).__name__, f" HTTP {status}" if status else "")

    if last_error:
        raise last_error

    raise PermanentError("All email providers failed without raising an exception")
