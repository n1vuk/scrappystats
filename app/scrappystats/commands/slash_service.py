
"""Slash command: /servicerecord for v2.0.0.

Formats the service history for a single Member.
"""
from ..models.member import Member
from typing import Literal
from ..services.report_service import build_service_reports
from ..log import log  # or wherever log lives
from ..discord_utils import interaction_response
from ..webhook.sender import post_webhook_message

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

_REPORT_BY_SUBCOMMAND = {
    "dailyreport": "daily",
    "weeklyreport": "weekly",
    "interimreport": "interim",
}

_REPORT_VALUES = set(_REPORT_BY_SUBCOMMAND.values())


def _resolve_report_period(payload: dict, fallback: ReportPeriod) -> ReportPeriod:
    data = payload.get("data", {})
    options = data.get("options") or []
    if options:
        sub = options[0]
        sub_name = sub.get("name")
        if sub_name in _REPORT_BY_SUBCOMMAND:
            return _REPORT_BY_SUBCOMMAND[sub_name]
        sub_options = sub.get("options") or []
        for opt in sub_options:
            if opt.get("name") == "period" and opt.get("value") in _REPORT_VALUES:
                return opt["value"]
    for opt in options:
        if opt.get("name") == "period" and opt.get("value") in _REPORT_VALUES:
            return opt["value"]
    return fallback


def handle_report_slash(payload: dict, period: ReportPeriod):
    """
    Thin adapter for slash commands.
    No business logic lives here.
    """
    guild_id = payload.get("guild_id")
    resolved_period = _resolve_report_period(payload, period)
    log.info(
        "Slash report requested: guild=%s period=%s",
        guild_id,
        resolved_period,
    )
    reports = build_service_reports(resolved_period, guild_id=guild_id)
    for alliance_id, message in reports:
        post_webhook_message(message, alliance_id=alliance_id)
    if not reports:
        return interaction_response(
            f"📊 {resolved_period.capitalize()} report: no changes recorded.",
            ephemeral=True,
        )
    content = "\n\n".join(message for _, message in reports)
    if len(content) > 1900:
        content = content[:1900].rstrip() + "\n\n(Report truncated for Discord.)"
    return interaction_response(
        content,
        ephemeral=True,
    )
