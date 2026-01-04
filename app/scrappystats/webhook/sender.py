import logging
import os
from typing import Optional

import requests

from ..config import load_config

log = logging.getLogger("scrappystats.webhook")

DEFAULT_TIMEOUT = 10
_WEBHOOK_ENV_VARS = ("DISCORD_WEBHOOK_URL",)


def _get_webhook_url(*, alliance_id: Optional[str] = None) -> Optional[str]:
    """
    Returns the configured webhook URL or None if not set.
    """
    for name in _WEBHOOK_ENV_VARS:
        url = os.getenv(name)
        if url:
            return url
    cfg = load_config()
    if alliance_id:
        for alliance in cfg.get("alliances", []):
            if str(alliance.get("id")) == str(alliance_id):
                url = alliance.get("webhook")
                if url:
                    return url
    return cfg.get("admin_webhook") or cfg.get("webhook")


def post_webhook_message(content: str, *, alliance_id: Optional[str] = None) -> None:
    """
    Post a plain-text message to the configured webhook.

    This is the ONLY supported webhook send path.
    All callers must use this function.
    """
    url = _get_webhook_url(alliance_id=alliance_id)

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
