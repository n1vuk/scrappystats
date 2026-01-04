"""
Event → message → webhook dispatch.

This is the ONLY place that:
- iterates events
- builds messages
- sends webhooks
"""

import logging
from typing import Dict, List, Any, Iterable

from ..webhook.sender import post_webhook_message
from ..webhook import messages

log = logging.getLogger("scrappystats.events")

DISCORD_MESSAGE_LIMIT = 2000
MESSAGE_SEPARATOR = "\n\n"


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


def _iter_message_batches(
    events: List[Dict[str, Any]],
    *,
    limit: int = DISCORD_MESSAGE_LIMIT,
    separator: str = MESSAGE_SEPARATOR,
) -> Iterable[str]:
    current: list[str] = []
    current_len = 0

    for event in events:
        message = _build_message(event)
        message_len = len(message)

        if message_len > limit:
            if current:
                yield separator.join(current)
                current = []
                current_len = 0
            for offset in range(0, message_len, limit):
                yield message[offset : offset + limit]
            continue

        if current:
            projected = current_len + len(separator) + message_len
        else:
            projected = message_len

        if projected > limit and current:
            yield separator.join(current)
            current = [message]
            current_len = message_len
            continue

        current.append(message)
        current_len = projected

    if current:
        yield separator.join(current)


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

    for idx, message in enumerate(_iter_message_batches(events), start=1):
        try:
            post_webhook_message(message, alliance_id=alliance_id)
            log.debug("Dispatched webhook batch %d", idx)

        except Exception:
            # This should basically never happen now, but if it does:
            log.exception(
                "Failed to dispatch webhook batch %d",
                idx,
            )

    log.info("Webhook dispatch complete (%d events)", len(events))
