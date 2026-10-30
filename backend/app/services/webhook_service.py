"""
Webhook (Slack/Discord) delivery adapter.
"""
import logging
from urllib.parse import urlparse

import requests

from app.services.errors import PermanentError, TransientError

logger = logging.getLogger(__name__)

SLACK_HOSTS = {"hooks.slack.com"}
DISCORD_HOSTS = {"discord.com", "discordapp.com"}


def _provider_for(hostname: str) -> str:
    if hostname in SLACK_HOSTS:
        return "slack"
    if hostname in DISCORD_HOSTS:
        return "discord"
    return "webhook"


def _mask_webhook_url(url: str) -> str:
    """Mask the webhook URL to avoid exposing secret tokens/paths in errors or logs."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.hostname or "webhook"
        last6 = url[-6:] if len(url) >= 6 else url
        return f"https://{host}/...{last6}"
    except Exception:
        return "https://[masked-webhook-url]"


def send_webhook(url: str, text: str) -> tuple[str, None]:
    """
    POST JSON to a Slack or Discord webhook URL.
    Returns (provider_name, None).
    Raises TransientError or PermanentError on failure.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    provider = _provider_for(hostname)
    masked_url = _mask_webhook_url(url)

    if hostname in DISCORD_HOSTS:
        payload = {"content": text}
    else:
        payload = {"text": text}

    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=10,
            allow_redirects=False,
        )
    except requests.exceptions.Timeout as exc:
        exc_type = type(exc).__name__
        raise TransientError(f"Webhook timeout ({exc_type}) for {masked_url}") from None
    except (requests.exceptions.ConnectionError, OSError) as exc:
        exc_type = type(exc).__name__
        raise TransientError(f"Webhook connection error ({exc_type}) for {masked_url}") from None
    except requests.exceptions.RequestException as exc:
        exc_type = type(exc).__name__
        raise TransientError(f"Webhook request error ({exc_type}) for {masked_url}") from None

    if resp.status_code == 429 or resp.status_code >= 500:
        raise TransientError(f"Webhook transient error: HTTP {resp.status_code} from {masked_url}")
    if resp.is_redirect or (300 <= resp.status_code < 400):
        raise PermanentError(f"Webhook redirect not followed: HTTP {resp.status_code} from {masked_url}", failover=False)
    if resp.status_code >= 400:
        raise PermanentError(f"Webhook permanent error: HTTP {resp.status_code} from {masked_url}", failover=False)

    logger.info(f"Webhook delivered via {provider}: HTTP {resp.status_code}")
    return provider, None

