
# v2.0.0 Detection Engine — Stage6 Finalized
from typing import Dict, List
from ..models.member import Member

RANK_ORDER = ["Agent", "Operative", "Premier", "Commodore", "Admiral"]
RANK_INDEX = {r.lower(): i for i, r in enumerate(RANK_ORDER)}

def _rank_value(rank: str) -> int:
    if not rank:
        return -1
    return RANK_INDEX.get(rank.lower(), -1)

def detect_member_events(previous_state: Dict[str, Member],
                         new_state: Dict[str, Member]):
    """Returns: joins, leaves, renames, promotions, demotions"""

    joins: List[Member] = []
    leaves: List[Member] = []
    renames: List[dict] = []
    promotions: List[dict] = []
    demotions: List[dict] = []

    prev_keys = set(previous_state.keys())
    new_keys = set(new_state.keys())

    # Joins
    for k in sorted(new_keys - prev_keys):
        joins.append(new_state[k])

    # Leaves
    for k in sorted(prev_keys - new_keys):
        leaves.append(previous_state[k])

    # Overlapping members
    for k in sorted(prev_keys & new_keys):
        old = previous_state[k]
        new = new_state[k]

        # Name change
        if old.name != new.name:
            renames.append({
                "member": new,
                "old_name": old.name,
                "new_name": new.name,
            })
            if old.name not in new.previous_names:
                new.previous_names.append(old.name)

        # Rank change
        if old.rank != new.rank:
            oldv = _rank_value(old.rank)
            newv = _rank_value(new.rank)
            if newv > oldv:
                promotions.append({
                    "member": new,
                    "old_rank": old.rank,
                    "new_rank": new.rank,
                })
            elif newv < oldv:
                demotions.append({
                    "member": new,
                    "old_rank": old.rank,
                    "new_rank": new.rank,
                })

    return joins, leaves, renames, promotions, demotions
