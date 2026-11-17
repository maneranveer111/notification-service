import logging

from app.celery_app import celery
from app.config import get_settings
from app.services import email_service
from app.services.email_service import _sanitize_error_str, mask_email
from app.services.errors import PermanentError, TransientError

logger = logging.getLogger(__name__)


@celery.task(name="system.send_email", bind=True, max_retries=3)
def send_system_email_task(self, to: str, subject: str, body: str):
    settings = get_settings()
    masked_to = mask_email(to)
    backend = settings.system_mail_backend
    task_id = getattr(getattr(self, "request", None), "id", "direct")

    logger.info(
        "System email task received [id=%s]: recipient=%s, subject=%r, backend=%s",
        task_id,
        masked_to,
        subject,
        backend,
    )

    if backend == "console":
        logger.info("CONSOLE MAIL to=%s subject=%s\n%s", to, subject, body)
        return

    if backend != "provider":
        logger.error(
            "system_mail_backend has an unrecognised value %r — expected 'provider' or 'console'. "
            "Email NOT sent. Set SYSTEM_MAIL_BACKEND=provider in .env.",
            backend,
        )
        return

    logger.info(
        "Provider request attempted: dispatching system email to %s via configured providers",
        masked_to,
    )
    try:
        provider_name, message_id = email_service.send_email(recipient=to, subject=subject, body=body)
        logger.info(
            "System email accepted by provider %s (message_id=%s) recipient=%s subject=%r",
            provider_name,
            message_id,
            masked_to,
            subject,
        )
    except TransientError as e:
        countdown = 30 * (2 ** self.request.retries)
        sanitized_err = _sanitize_error_str(str(e))
        logger.warning(
            "Transient failure sending system email to %s (attempt %d/3), retrying in %ds: %s",
            masked_to,
            self.request.retries + 1,
            countdown,
            sanitized_err,
        )
        raise self.retry(exc=e, countdown=countdown)
    except PermanentError as e:
        sanitized_err = _sanitize_error_str(str(e))
        logger.error(
            "Permanent failure sending system email to %s subject=%r via provider: %s — "
            "check BREVO_FROM_EMAIL is verified in Brevo Senders & Domains and credentials are valid",
            masked_to,
            subject,
            sanitized_err,
        )
        # Fail the task. Permanent errors must not be converted into endless retries.
        raise
    except Exception as e:
        sanitized_err = _sanitize_error_str(str(e))
        logger.error(
            "Unexpected error sending system email to %s subject=%r: %s",
            masked_to,
            subject,
            sanitized_err,
            exc_info=True,
        )
        # Fail the task. Unexpected sending errors must not be silently swallowed.
        raise

