"""
Trek-themed webhook message builders.

RULES:
- No network calls
- No logging
- No environment access
- Never raise on bad input
- Always return a string
"""

from typing import Dict, Optional, Any, Iterable

from ..models.member import Member


def _safe(event: Dict[str, Any], key: str, default: str = "Unknown") -> str:
    val = event.get(key)
    return str(val) if val not in (None, "") else default


def _get_member(event: Dict[str, Any]) -> Optional[Member]:
    member = event.get("member")
    return member if isinstance(member, Member) else None


def _member_name(member: Optional[Member], event: Dict[str, Any]) -> str:
    if member is not None:
        return str(getattr(member, "name", "Unknown") or "Unknown")
    return _safe(event, "member_name")


def _member_rank(member: Optional[Member], event: Dict[str, Any]) -> str:
    if member is not None:
        return str(getattr(member, "rank", "Unknown") or "Unknown")
    return _safe(event, "rank")


def _member_level(member: Optional[Member], event: Dict[str, Any]) -> str:
    if member is not None:
        return str(getattr(member, "level", "Unknown") or "Unknown")
    return _safe(event, "level")


def build_member_joined(event: Dict[str, Any]) -> str:
    return build_join_batch([event])


def build_member_left(event: Dict[str, Any]) -> str:
    name = _safe(event, "member_name")
    alliance = _safe(event, "alliance_name")
    return f"📡 **Departure logged**\n{name} has left **{alliance}**."


def build_rank_change(event: Dict[str, Any]) -> str:
    name = _safe(event, "member_name")
    old = _safe(event, "old_rank")
    new = _safe(event, "new_rank")
    return f"🎖 **Rank update**\n{name}: {old} → **{new}**"


def build_rejoin(event: Dict[str, Any]) -> str:
    member = _get_member(event)
    name = _member_name(member, event)
    level = _member_level(member, event)
    rank = _member_rank(member, event)
    return f"🖖 **Officer reinstated**\n{name} returned at Level {level} ({rank})."


def build_leave(event: Dict[str, Any]) -> str:
    member = _get_member(event)
    name = _member_name(member, event)
    level = _member_level(member, event)
    return f"📡 **Departure logged**\n{name} has left (last level {level})."


def build_rename(event: Dict[str, Any]) -> str:
    member = _get_member(event)
    old_name = _safe(event, "old_name")
    new_name = _safe(event, "new_name")
    if member is not None and new_name == "Unknown":
        new_name = _member_name(member, event)
    return f"🗂 **Identity update**\n{old_name} is now **{new_name}**."


def build_promotion(event: Dict[str, Any]) -> str:
    member = _get_member(event)
    name = _member_name(member, event)
    old_rank = _safe(event, "old_rank")
    new_rank = _safe(event, "new_rank")
    if new_rank == "Unknown":
        new_rank = _member_rank(member, event)
    return f"🎖 **Rank update**\n{name}: {old_rank} → **{new_rank}**"


def build_demotion(event: Dict[str, Any]) -> str:
    member = _get_member(event)
    name = _member_name(member, event)
    old_rank = _safe(event, "old_rank")
    new_rank = _safe(event, "new_rank")
    if new_rank == "Unknown":
        new_rank = _member_rank(member, event)
    return f"📉 **Rank update**\n{name}: {old_rank} → **{new_rank}**"


def build_level_up(event: Dict[str, Any]) -> str:
    member = _get_member(event)
    name = _member_name(member, event)
    old_level = _safe(event, "old_level")
    new_level = _safe(event, "new_level")
    if new_level == "Unknown":
        new_level = _member_level(member, event)
    return f"📈 **Level up**\n{name}: {old_level} → **{new_level}**"


def build_generic_event(event: Dict[str, Any]) -> str:
    etype = _safe(event, "type", "unknown")
    return f"📟 **Event received**\nType: `{etype}`"


def _header_line(header: str, lines: Iterable[str]) -> str:
    return "\n".join([header, *lines])


def build_join_batch(events: list[Dict[str, Any]]) -> str:
    if not events:
        return (
            "🖖 **Counselor Troi to Bridge** New Commanders have beamed aboard **Unknown**."
        )
    alliance = _safe(events[0], "alliance_name")
    names = []
    for event in events:
        member = _get_member(event)
        name = _member_name(member, event)
        level = _member_level(member, event)
        names.append(f"{name} (Level {level})")
    plural = len(names) != 1
    if plural:
        body = (
            "New Commanders have beamed aboard. They have been ordered to sickbay for their "
            "routine exams. Let's welcome them to"
        )
    else:
        body = (
            "A new Commander has beamed aboard. They have been ordered to sickbay for their "
            "routine exams. Let's welcome them to"
        )
    header = f"🖖 **Counselor Troi to Bridge** {body} **{alliance}**."
    return _header_line(header, (f"- {name}" for name in names))


def build_rejoin_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        member = _get_member(event)
        name = _member_name(member, event)
        level = _member_level(member, event)
        rank = _member_rank(member, event)
        lines.append(f"- {name} returned at Level {level} ({rank}).")
    return _header_line("🖖 **Officer reinstated**", lines)


def build_leave_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        member = _get_member(event)
        name = _member_name(member, event)
        level = _member_level(member, event)
        lines.append(f"- {name} has left (last level {level}).")
    return _header_line("📡 **Departure logged**", lines)


def build_rename_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        member = _get_member(event)
        old_name = _safe(event, "old_name")
        new_name = _safe(event, "new_name")
        if member is not None and new_name == "Unknown":
            new_name = _member_name(member, event)
        lines.append(f"- {old_name} is now **{new_name}**.")
    return _header_line("🗂 **Identity update**", lines)


def build_rename_review_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        old_name = _safe(event, "old_name")
        new_name = _safe(event, "new_name")
        reason = _safe(event, "reason")
        notes = event.get("notes") or "no additional metrics"
        lines.append(f"- Possible rename: {old_name} → **{new_name}** ({reason}; {notes})")
    return _header_line("🛟 **Rename review needed**", lines)


def build_promotion_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        member = _get_member(event)
        name = _member_name(member, event)
        old_rank = _safe(event, "old_rank")
        new_rank = _safe(event, "new_rank")
        if new_rank == "Unknown":
            new_rank = _member_rank(member, event)
        lines.append(f"- {name}: {old_rank} → **{new_rank}**")
    return _header_line("🎖 **Rank update**", lines)


def build_demotion_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        member = _get_member(event)
        name = _member_name(member, event)
        old_rank = _safe(event, "old_rank")
        new_rank = _safe(event, "new_rank")
        if new_rank == "Unknown":
            new_rank = _member_rank(member, event)
        lines.append(f"- {name}: {old_rank} → **{new_rank}**")
    return _header_line("📉 **Rank update**", lines)


def build_level_up_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        member = _get_member(event)
        name = _member_name(member, event)
        old_level = _safe(event, "old_level")
        new_level = _safe(event, "new_level")
        if new_level == "Unknown":
            new_level = _member_level(member, event)
        lines.append(f"- {name}: {old_level} → **{new_level}**")
    return _header_line("📈 **Level up**", lines)


def build_member_left_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        name = _safe(event, "member_name")
        alliance = _safe(event, "alliance_name")
        lines.append(f"- {name} has left **{alliance}**.")
    return _header_line("📡 **Departure logged**", lines)


def build_rank_change_batch(events: list[Dict[str, Any]]) -> str:
    lines = []
    for event in events:
        name = _safe(event, "member_name")
        old = _safe(event, "old_rank")
        new = _safe(event, "new_rank")
        lines.append(f"- {name}: {old} → **{new}**")
    return _header_line("🎖 **Rank update**", lines)


def build_generic_batch(events: list[Dict[str, Any]]) -> str:
    lines = [f"- Type: `{_safe(event, 'type', 'unknown')}`" for event in events]
    return _header_line("📟 **Event received**", lines)
