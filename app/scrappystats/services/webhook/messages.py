
"""Trek-themed webhook message builders for v2.0.0-dev."""
from ...models.member import Member


def build_join_message(name: str, level: int, stardate: str) -> str:
    return f"""🖖 Chief of Personnel: A new officer has beamed aboard!
Welcome **{name}** — Level {level}.
Stardate {stardate}
"""


def build_rejoin_message(name: str, level: int, previous_rank: str, stardate: str) -> str:
    return f"""🖖 Chief of Personnel: An officer has returned to duty.
**{name}** — reinstated at Rank {previous_rank}, Level {level}.
Stardate {stardate}
"""


def build_leave_message(name: str, level: int, stardate: str) -> str:
    return f"""🖖 Chief of Personnel: An officer has departed the alliance.
**{name}** — Final recorded level: {level}.
Stardate {stardate}
"""


def build_rename_message(name: str, old_name: str, new_name: str, stardate: str) -> str:
    return f"""🖖 Chief of Personnel: Identity records updated.
**{old_name}** is now known as **{new_name}**.
Stardate {stardate}
"""


def build_promotion_message(name: str, old_rank: str, new_rank: str, stardate: str) -> str:
    return f"""🖖 Command Update: Officer promoted.
**{name}** — {old_rank} ➜ {new_rank}.
Stardate {stardate}
"""


def build_demotion_message(name: str, old_rank: str, new_rank: str, stardate: str) -> str:
    return f"""🖖 Command Update: Officer reassigned.
**{name}** — {old_rank} ➜ {new_rank}.
Stardate {stardate}
"""


def build_level_up_message(name: str, old_level: int, new_level: int, stardate: str) -> str:
    return f"""🖖 Performance Report: Officer level increased.
**{name}** — Level {old_level} ➜ Level {new_level}.
Stardate {stardate}
"""


def build_join_message_for_member(member: Member, stardate: str) -> str:
    level = int(getattr(member, "level", 0) or 0)
    return build_join_message(member.name, level, stardate)


def build_rejoin_message_for_member(member: Member, previous_rank: str, stardate: str) -> str:
    level = int(getattr(member, "level", 0) or 0)
    return build_rejoin_message(member.name, level, previous_rank, stardate)


def build_leave_message_for_member(member: Member, stardate: str) -> str:
    level = int(getattr(member, "level", 0) or 0)
    return build_leave_message(member.name, level, stardate)


def build_rename_message_for_member(member: Member, old_name: str, new_name: str, stardate: str) -> str:
    return build_rename_message(member.name, old_name, new_name, stardate)


def build_promotion_message_for_member(member: Member, old_rank: str, new_rank: str, stardate: str) -> str:
    return build_promotion_message(member.name, old_rank, new_rank, stardate)


def build_demotion_message_for_member(member: Member, old_rank: str, new_rank: str, stardate: str) -> str:
    return build_demotion_message(member.name, old_rank, new_rank, stardate)


def build_level_up_message_for_member(member: Member, old_level: int, new_level: int, stardate: str) -> str:
    return build_level_up_message(member.name, old_level, new_level, stardate)


__all__ = [
    "build_join_message",
    "build_rejoin_message",
    "build_leave_message",
    "build_rename_message",
    "build_promotion_message",
    "build_demotion_message",
    "build_level_up_message",
    "build_join_message_for_member",
    "build_rejoin_message_for_member",
    "build_leave_message_for_member",
    "build_rename_message_for_member",
    "build_promotion_message_for_member",
    "build_demotion_message_for_member",
    "build_level_up_message_for_member",
]
