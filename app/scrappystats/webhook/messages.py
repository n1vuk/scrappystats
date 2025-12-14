"""
Trek-themed webhook message builders.

RULES:
- No network calls
- No logging
- No environment access
- Never raise on bad input
- Always return a string
"""

from typing import Dict


def _safe(event: Dict, key: str, default: str = "Unknown") -> str:
    val = event.get(key)
    return str(val) if val not in (None, "") else default


def build_member_joined(event: Dict) -> str:
    name = _safe(event, "member_name")
    alliance = _safe(event, "alliance_name")
    return f"🖖 **Incoming transmission**\n{name} has joined **{alliance}**."


def build_member_left(event: Dict) -> str:
    name = _safe(event, "member_name")
    alliance = _safe(event, "alliance_name")
    return f"📡 **Departure logged**\n{name} has left **{alliance}**."


def build_rank_change(event: Dict) -> str:
    name = _safe(event, "member_name")
    old = _safe(event, "old_rank")
    new = _safe(event, "new_rank")
    return f"🎖 **Rank update**\n{name}: {old} → **{new}**"


def build_generic_event(event: Dict) -> str:
    etype = _safe(event, "type", "unknown")
    return f"📟 **Event received**\nType: `{etype}`"
