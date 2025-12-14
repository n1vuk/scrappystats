import logging
import os
import requests
from typing import Optional

log = logging.getLogger("scrappystats.webhook")

DEFAULT_TIMEOUT = 10


def _get_webhook_url() -> Optional[str]:
    """
    Returns the configured webhook URL or None if not set.
    """
    return os.getenv("SCRAPPYSTATS_WEBHOOK_URL")


def post_webhook_message(content: str) -> None:
    """
    Post a plain-text message to the configured webhook.

    This is the ONLY supported webhook send path.
    All callers must use this function.
    """
    url = _get_webhook_url()

    if not url:
        log.warning("[webhook] No webhook URL configured; skipping message")
        return

    payload = {
        "content": content
    }

    try:
        log.info("[webhook] Sending message (%d chars)", len(content))
        resp = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)

        if resp.status_code >= 400:
            log.error(
                "[webhook] HTTP %s from webhook: %s",
                resp.status_code,
                resp.text,
            )
        else:
            log.info("[webhook] Message delivered successfully")

    except requests.RequestException:
        log.exception("[webhook] Request to webhook failed")
    except Exception:
        log.exception("[webhook] Unexpected error while sending webhook")
