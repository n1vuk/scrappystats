
"""Slash command: /fullroster for v2.0.0.

Formats the current alliance roster from the v2 state structure.
"""
from typing import Dict
from ..models.member import Member

# Rank order from highest to lowest for display
RANK_DISPLAY_ORDER = [
    "Admiral",
    "Commodore",
    "Premier",
    "Operative",
    "Agent",
]
RANK_INDEX = {name: i for i, name in enumerate(RANK_DISPLAY_ORDER)}

def _deserialize_members(members_raw: Dict[str, dict]):
    members = []
    for data in members_raw.values():
        members.append(Member.from_json(data))
    return members

def full_roster_command(alliance_state: dict) -> str:
    """Build a simple text roster table from the v2 alliance_state dict.

    alliance_state is expected to be the dict returned by
    scrappystats.storage.state.load_state(alliance_id).
    """
    members_raw = alliance_state.get("members", {}) or {}
    members = _deserialize_members(members_raw)

    # Sort by rank (highest first), then level desc, then name
    def sort_key(m: Member):
        rank_idx = RANK_INDEX.get(m.rank, len(RANK_DISPLAY_ORDER))
        return (rank_idx, -int(m.level or 0), m.name.lower())

    members.sort(key=sort_key)

    def format_join_date(value: str) -> str:
        if not value:
            return "-"
        if "T" in value:
            return value.split("T", 1)[0]
        return value

    lines = []
    lines.append("📋 Full Roster")
    lines.append("```")
    lines.append(f"{'Rank':<10} {'Lvl':>3}  {'Last Join':<10} {'Orig Join':<10} Name")
    lines.append("-" * 58)
    for m in members:
        lvl = m.level if isinstance(m.level, int) else int(m.level or 0)
        last_join = format_join_date(m.last_join_date)
        orig_join = format_join_date(m.original_join_date)
        lines.append(
            f"{m.rank:<10} {lvl:>3}  {last_join:<10} {orig_join:<10} {m.name}"
        )
    lines.append("```")
    return "\n".join(lines)

__all__ = ["full_roster_command"]
