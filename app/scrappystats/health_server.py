import logging
from .version import __version__
from .webhook.sender import post_webhook_message

log = logging.getLogger("scrappystats.health")

_READY_WEBHOOK_SENT = False


@app.get("/health/ready")
def ready():
    global _READY_WEBHOOK_SENT

    if not _READY_WEBHOOK_SENT:
        try:
            post_webhook_message(
                f"🟢 ScrappyStats is online and ready (v{__version__})"
            )
            _READY_WEBHOOK_SENT = True
            log.info("Ready webhook sent")
        except Exception:
            # sender already logs, but we guard anyway
            log.exception("Failed to send ready webhook")

    return {
        "status": "ready",
        "service": "scrappystats",
        "version": __version__,
    }
