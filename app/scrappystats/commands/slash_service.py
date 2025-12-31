
"""Slash command: /servicerecord for v2.0.0.

Formats the service history for a single Member.
"""
from ..models.member import Member
from typing import Literal
from ..services.report_service import run_service_report
from ..log import log  # or wherever log lives
from ..discord_utils import interaction_response

def service_record_command(member: Member) -> str:
    """Return a formatted service record for the given Member instance."""
    lines = []
    lines.append(f"📘 Service Record: {member.name}")
    lines.append(f"Current Rank: {member.rank}")
    lines.append(f"Current Level: {member.level}")
    lines.append(f"Original Join: {member.original_join_date}")
    lines.append(f"Last Join: {member.last_join_date}")
    if getattr(member, "previous_names", None):
        lines.append(f"Previous Names: {', '.join(member.previous_names)}")
    lines.append("")

    events = list(getattr(member, "service_events", []) or [])
    if not events:
        lines.append("No recorded events yet.")
        return "\n".join(lines)

    # Sort by timestamp if present
    events.sort(key=lambda e: e.get("timestamp", ""))

    lines.append("Events:")
    for ev in events:
        etype = ev.get("type", "")
        ts = ev.get("timestamp", "")
        desc = None

        if etype == "join":
            desc = "Joined the alliance"
        elif etype == "leave":
            desc = "Left the alliance"
        elif etype == "rename":
            desc = f"Renamed from {ev.get('old_name')} to {ev.get('new_name')}"
        elif etype == "promotion":
            desc = f"Promoted from {ev.get('old_rank')} to {ev.get('new_rank')}"
        elif etype == "demotion":
            desc = f"Demoted from {ev.get('old_rank')} to {ev.get('new_rank')}"
        else:
            # Fallback: show raw type if something new appears
            desc = etype or "Event"

        lines.append(f"{ts} — {desc}")

    return "\n".join(lines)

__all__ = ["service_record_command"]


ReportPeriod = Literal["daily", "weekly", "interim"]


def handle_report_slash(payload: dict, period: ReportPeriod):
    """
    Thin adapter for slash commands.
    No business logic lives here.
    """
    guild_id = payload.get("guild_id")
    log.info("Slash report requested: guild=%s period=%s", guild_id, period)
    run_service_report(period)
    return interaction_response(
        f"📊 {period.capitalize()} report dispatched. Check the configured webhook.",
        ephemeral=True,
    )
