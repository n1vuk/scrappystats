
"""Event dispatcher for v2.0.0-dev.

Takes normalized event dicts from the sync pipeline and sends
Trek-themed messages to the configured webhook.
"""
from typing import List, Dict, Any

from ..models.member import Member
from ..webhook.messages import (
    build_join_message_for_member,
    build_rejoin_message_for_member,
    build_leave_message_for_member,
    build_rename_message_for_member,
    build_promotion_message_for_member,
    build_demotion_message_for_member,
    build_level_up_message_for_member,
)
from ..webhook.sender import post_webhook_message


def dispatch_webhook_events(events: List[Dict[str, Any]], stardate: str) -> None:
    """Dispatch all events to the webhook as human-readable messages.

    Each event dict is expected to contain:
      - type: one of 'join', 'leave', 'rejoin',
               'rename', 'promotion', 'demotion', 'level_up'
      - member: Member
      - other fields depending on type (old_name, new_name, etc.)
    """
    for ev in events:
        etype = ev.get("type")
        member: Member = ev.get("member")  # type: ignore[assignment]

        if not isinstance(member, Member):
            continue

        if etype == "join":
            content = build_join_message_for_member(member, stardate)
        elif etype == "rejoin":
            last_leave = ev.get("last_leave") or {}
            previous_rank = last_leave.get("old_rank") or last_leave.get("previous_rank") or member.rank
            content = build_rejoin_message_for_member(member, previous_rank, stardate)
        elif etype == "leave":
            content = build_leave_message_for_member(member, stardate)
        elif etype == "rename":
            content = build_rename_message_for_member(
                member,
                ev.get("old_name"),
                ev.get("new_name"),
                stardate,
            )
        elif etype == "promotion":
            content = build_promotion_message_for_member(
                member,
                ev.get("old_rank"),
                ev.get("new_rank"),
                stardate,
            )
        elif etype == "demotion":
            content = build_demotion_message_for_member(
                member,
                ev.get("old_rank"),
                ev.get("new_rank"),
                stardate,
            )
        elif etype == "level_up":
            content = build_level_up_message_for_member(
                member,
                ev.get("old_level"),
                ev.get("new_level"),
                stardate,
            )
        else:
            # Unknown / unsupported event type
            continue

        try:
            post_webhook_message(content)
        except Exception as exc:
            print(f"[dispatch_webhook_events] Failed to send {etype}: {exc}")
