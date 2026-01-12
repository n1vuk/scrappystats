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
    in_code_block = False

    def append_line(line: str) -> None:
        nonlocal current_len
        current.append(line)
        current_len += len(line) + 1

    def finalize_chunk() -> None:
        nonlocal current, current_len
        chunks.append("\n".join(current))
        current = []
        current_len = 0

    def close_code_block_for_chunk() -> None:
        if not in_code_block:
            return
        append_line("```")

    for line in content.splitlines():
        line_len = len(line)
        extra_close_len = 4 if in_code_block else 0
        if current and current_len + line_len + 1 + extra_close_len > MAX_CONTENT_LEN:
            if in_code_block:
                close_code_block_for_chunk()
            finalize_chunk()
            if in_code_block:
                append_line("```")
        if line_len >= MAX_CONTENT_LEN:
            if current:
                if in_code_block:
                    close_code_block_for_chunk()
                finalize_chunk()
                if in_code_block:
                    append_line("```")
            for i in range(0, line_len, MAX_CONTENT_LEN):
                segment = line[i : i + MAX_CONTENT_LEN]
                if in_code_block:
                    chunks.append("\n".join(["```", segment, "```"]))
                else:
                    chunks.append(segment)
            continue
        append_line(line)
        if line.count("```") % 2 == 1:
            in_code_block = not in_code_block
    if current:
        if in_code_block:
            if current_len + 4 > MAX_CONTENT_LEN:
                finalize_chunk()
                chunks.append("```")
            else:
                append_line("```")
        finalize_chunk()
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
