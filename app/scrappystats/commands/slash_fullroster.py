
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

    lines = []
    lines.append("📋 Full Roster")
    lines.append("```")
    lines.append(f"{'Rank':<10} {'Lvl':>3}  Name")
    lines.append("-" * 32)
    for m in members:
        lvl = m.level if isinstance(m.level, int) else int(m.level or 0)
        lines.append(f"{m.rank:<10} {lvl:>3}  {m.name}")
    lines.append("```")
    return "\n".join(lines)

__all__ = ["full_roster_command"]
