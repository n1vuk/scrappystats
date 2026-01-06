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


def _iter_message_batches(
    messages_to_send: List[str],
    *,
    limit: int = DISCORD_MESSAGE_LIMIT,
    separator: str = MESSAGE_SEPARATOR,
) -> Iterable[str]:
    current: list[str] = []
    current_len = 0

    for message in messages_to_send:
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


def _build_messages(events: List[Dict[str, Any]]) -> list[str]:
    messages_out: list[str] = []
    grouped: dict[str, list[Dict[str, Any]]] = {}
    type_order: list[str] = []
    batch_builders = {
        "join": messages.build_join_batch,
        "rejoin": messages.build_rejoin_batch,
        "leave": messages.build_leave_batch,
        "rename": messages.build_rename_batch,
        "rename_review": messages.build_rename_review_batch,
        "promotion": messages.build_promotion_batch,
        "demotion": messages.build_demotion_batch,
        "level_up": messages.build_level_up_batch,
        "member_joined": messages.build_join_batch,
        "member_left": messages.build_member_left_batch,
        "rank_change": messages.build_rank_change_batch,
        "unknown": messages.build_generic_batch,
    }

    for event in events:
        etype = event.get("type", "unknown")
        if etype not in grouped:
            grouped[etype] = []
            type_order.append(etype)
        grouped[etype].append(event)

    for etype in type_order:
        builder = batch_builders.get(etype, messages.build_generic_batch)

        current: list[Dict[str, Any]] = []
        for event in grouped[etype]:
            candidate = current + [event]
            message = builder(candidate)
            if len(message) > DISCORD_MESSAGE_LIMIT and current:
                messages_out.append(builder(current))
                current = [event]
            else:
                current = candidate

        if current:
            messages_out.append(builder(current))

    return messages_out


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

    messages_to_send = _build_messages(events)
    for idx, message in enumerate(_iter_message_batches(messages_to_send), start=1):
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
