"""
Event → message → webhook dispatch.

This is the ONLY place that:
- iterates events
- builds messages
- sends webhooks
"""

import logging
from typing import Dict, List, Any

from ..webhook.sender import post_webhook_message
from ..webhook import messages

log = logging.getLogger("scrappystats.events")


_EVENT_BUILDERS = {
    "join": messages.build_join,
    "rejoin": messages.build_rejoin,
    "leave": messages.build_leave,
    "rename": messages.build_rename,
    "promotion": messages.build_promotion,
    "demotion": messages.build_demotion,
    "level_up": messages.build_level_up,
    "member_joined": messages.build_member_joined,
    "member_left": messages.build_member_left,
    "rank_change": messages.build_rank_change,
}


def _build_message(event: Dict[str, Any]) -> str:
    etype = event.get("type", "unknown")
    builder = _EVENT_BUILDERS.get(etype, messages.build_generic_event)
    return builder(event)


def dispatch_webhook_events(
    events: List[Dict[str, Any]],
    stardate: str,
    *,
    alliance_id: str | None = None,
) -> None:
    """
    Dispatch a batch of events to the webhook.

    - Never raises
    - Logs all failures
    - Continues processing remaining events
    """
    if not events:
        log.info("No events to dispatch for stardate %s", stardate)
        return

    log.info("Dispatching %d webhook events for stardate %s", len(events), stardate)

    for idx, event in enumerate(events, start=1):
        try:
            message = _build_message(event)
            post_webhook_message(message, alliance_id=alliance_id)
            log.debug("Dispatched event %d/%d", idx, len(events))

        except Exception:
            # This should basically never happen now, but if it does:
            log.exception(
                "Failed to dispatch event %d/%d: %r",
                idx,
                len(events),
                event,
            )

    log.info("Webhook dispatch complete (%d events)", len(events))
