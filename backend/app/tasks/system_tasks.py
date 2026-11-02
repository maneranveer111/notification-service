import logging

from app.celery_app import celery
from app.config import get_settings
from app.services import email_service
from app.services.errors import PermanentError, TransientError

logger = logging.getLogger(__name__)


@celery.task(name="system.send_email", bind=True, max_retries=3)
def send_system_email_task(self, to: str, subject: str, body: str):
    settings = get_settings()
    if settings.system_mail_backend == "console":
        logger.info("CONSOLE MAIL to=%s subject=%s\n%s", to, subject, body)
        return

    try:
        email_service.send_email(to=to, subject=subject, body=body)
    except TransientError as e:
        countdown = 30 * (2 ** self.request.retries)
        raise self.retry(exc=e, countdown=countdown)
    except PermanentError:
        logger.error("Permanent mail failure to=%s subject=%s", to, subject)

