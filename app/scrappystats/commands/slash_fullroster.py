
"""Slash command: /fullroster for v2.0.0.

Formats the current alliance roster from the v2 state structure.
"""
from typing import Dict, List
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

def full_roster_messages(
    alliance_state: dict,
    *,
    name_overrides: dict | None = None,
    active_names: set[str] | None = None,
) -> List[str]:
    """Build paginated roster messages from the v2 alliance_state dict.

    alliance_state is expected to be the dict returned by
    scrappystats.storage.state.load_state(alliance_id).
    """
    members_raw = alliance_state.get("members", {}) or {}
    members = _deserialize_members(members_raw)
    overrides = name_overrides or {}
    if active_names is not None:
        members = [member for member in members if member.name in active_names]

    # Sort by rank (highest first), then level desc, then name
    def sort_key(m: Member):
        rank_idx = RANK_INDEX.get(m.rank, len(RANK_DISPLAY_ORDER))
        display_name = overrides.get(m.uuid, m.name)
        return (rank_idx, -int(m.level or 0), display_name.lower())

    members.sort(key=sort_key)

    def format_join_date(value: str) -> str:
        if not value:
            return "-"
        if "T" in value:
            return value.split("T", 1)[0]
        return value

    max_length = 1900
    date_width = 18
    header = (
        f"{'Name':<20} {'Rank':<10} {'Lvl':>3} {'Power':>8}  "
        f"{'Last Join':<{date_width}} {'Orig Join':<{date_width}}"
    )
    separator = "-" * len(header)

    def build_intro(first: bool) -> List[str]:
        title = "📋 Full Roster" if first else "📋 Full Roster (cont.)"
        return [title, "```", header, separator]

    chunks: List[str] = []
    current = build_intro(True)

    for m in members:
        lvl = m.level if isinstance(m.level, int) else int(m.level or 0)
        orig_join = format_join_date(m.original_join_date)
        last_join = format_join_date(m.last_join_date)
        display_name = overrides.get(m.uuid, m.name)
        power = m.power if isinstance(m.power, int) else int(m.power or 0)
        line = (
            f"{display_name:<20} {m.rank:<10} {lvl:>3} {power:>8}  "
            f"{last_join:<{date_width}} {orig_join:<{date_width}}"
        )
        tentative = "\n".join(current + [line, "```"])
        if len(tentative) > max_length and len(current) > 4:
            chunks.append("\n".join(current + ["```"]))
            current = build_intro(False)
        current.append(line)

    chunks.append("\n".join(current + ["```"]))
    return chunks


__all__ = ["full_roster_messages"]
