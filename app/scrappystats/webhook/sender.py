
"""Simple webhook sender for ScrappyStats v2.0.0-dev."""
import os
import requests


_WEBHOOK_ENV_VARS = [
    "SCRAPPYSTATS_WEBHOOK_URL",
    "DISCORD_WEBHOOK_URL",
]


def _get_webhook_url() -> str | None:
    for name in _WEBHOOK_ENV_VARS:
        url = os.getenv(name)
        if url:
            return url
    return None


def post_webhook_message(content: str) -> None:
    """Post a simple text message to the configured webhook URL.

    If no webhook URL is configured, this function logs and returns
    without raising an exception.
    """
    url = _get_webhook_url()
    if not url:
        print("[webhook.sender] No webhook URL configured; skipping message.")
        return

    payload = {"content": content}
    try:
        resp = requests.post(url, json=payload, timeout=10)
    except Exception as exc:
        print(f"[webhook.sender] Error sending webhook: {exc}")
        return

    if resp.status_code >= 400:
        print(f"[webhook.sender] Webhook returned {resp.status_code}: {resp.text}")
