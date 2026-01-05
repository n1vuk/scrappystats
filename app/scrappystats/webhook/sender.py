import logging
import os
from typing import Optional

import requests

from ..config import load_config, iter_alliances

log = logging.getLogger("scrappystats.webhook")

DEFAULT_TIMEOUT = 10
_WEBHOOK_ENV_VARS = ("DISCORD_WEBHOOK_URL",)
MAX_CONTENT_LEN = 1900


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
        for alliance in iter_alliances(cfg):
            if str(alliance.get("id")) == str(alliance_id):
                url = alliance.get("webhook")
                if url:
                    return url
    return cfg.get("admin_webhook") or cfg.get("webhook")


def _chunk_message(content: str) -> list[str]:
    if len(content) <= MAX_CONTENT_LEN:
        return [content]

    chunks = []
    current = []
    current_len = 0
    for line in content.splitlines():
        line_len = len(line)
        if current and current_len + line_len + 1 > MAX_CONTENT_LEN:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        if line_len >= MAX_CONTENT_LEN:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            for i in range(0, line_len, MAX_CONTENT_LEN):
                chunks.append(line[i : i + MAX_CONTENT_LEN])
            continue
        current.append(line)
        current_len += line_len + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


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

    try:
        chunks = _chunk_message(content)
        log.info("[webhook] Sending message (%d chars, %d chunk(s))", len(content), len(chunks))
        for idx, chunk in enumerate(chunks, start=1):
            payload = {"content": chunk}
            resp = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)

            if resp.status_code >= 400:
                log.error(
                    "[webhook] HTTP %s from webhook (chunk %d/%d): %s",
                    resp.status_code,
                    idx,
                    len(chunks),
                    resp.text,
                )
            else:
                log.info(
                    "[webhook] Message chunk %d/%d delivered successfully",
                    idx,
                    len(chunks),
                )

    except requests.RequestException:
        log.exception("[webhook] Request to webhook failed")
    except Exception:
        log.exception("[webhook] Unexpected error while sending webhook")
