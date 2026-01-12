
"""Slash command: /servicerecord for v2.0.0.

Formats the service history for a single Member.
"""
from datetime import date, datetime, timezone
from typing import Literal

from ..models.member import Member
from ..services.report_common import build_table_from_rows
from ..services.report_service import build_service_reports
from ..log import log  # or wherever log lives
from ..discord_utils import interaction_response
from ..webhook.sender import post_webhook_message

def _format_timestamp(raw: str | None) -> str:
    if not raw:
        return "Unknown"
    value = str(raw).strip()
    value = value.replace(" ", "T")
    if value.endswith("Z") and "+" in value:
        value = value[:-1]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%b %d, %Y %H:%M UTC")
    except ValueError:
        pass
    try:
        parsed_date = date.fromisoformat(value)
        return parsed_date.strftime("%b %d, %Y")
    except ValueError:
        return value


def _format_join_date(raw: str | None) -> str:
    if not raw:
        return "Unknown"
    value = str(raw).strip()
    value = value.replace(" ", "T")
    if value.endswith("Z") and "+" in value:
        value = value[:-1]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.date().strftime("%b %d, %Y")
    except ValueError:
        pass
    try:
        parsed_date = date.fromisoformat(value.split("T", 1)[0])
        return parsed_date.strftime("%b %d, %Y")
    except ValueError:
        return value


def _format_number(value: int | str | None) -> str:
    if value is None:
        return "0"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if cleaned.isdigit():
            return f"{int(cleaned):,}"
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return str(value)


def _format_contribution_row(label: str, data: dict) -> list[str]:
    return {
        "period": label,
        "helps": _format_number(data.get("helps", 0)),
        "rss": _format_number(data.get("rss", 0)),
        "iso": _format_number(data.get("iso", 0)),
        "resources_mined": _format_number(data.get("resources_mined", 0)),
    }


def service_record_command(
    member: Member,
    *,
    power: int | str | None = None,
    max_power: int | None = None,
    power_destroyed: int | None = None,
    arena_rating: int | None = None,
    assessment_rank: int | None = None,
    missions_completed: int | None = None,
    resources_mined: int | None = None,
    alliance_helps_sent: int | None = None,
    power_since_join: int | None = None,
    power_today: int | None = None,
    power_7: int | None = None,
    power_30: int | None = None,
    contributions_total: dict | None = None,
    contributions_30: dict | None = None,
    contributions_7: dict | None = None,
    contributions_1: dict | None = None,
) -> str:
    """Return a formatted service record for the given Member instance."""
    lines = []
    lines.append(f"📘 **Service Record:** {member.name}")
    lines.append(f"**Current Rank:** {member.rank}")
    lines.append(f"**Current Level:** {member.level}")
    if power is None:
        power = getattr(member, "power", 0)
    power_value = power if isinstance(power, int) else int(power or 0)
    lines.append(f"**Current Power:** {_format_number(power_value)}")
    if max_power is None:
        max_power = power_value
    lines.append(f"**Max Power:** {_format_number(max_power)}")
    lines.append(f"**Power Destroyed:** {_format_number(power_destroyed)}")
    lines.append(f"**Arena Rating:** {_format_number(arena_rating)}")
    lines.append(f"**Assessment Rank:** {_format_number(assessment_rank)}")
    lines.append(f"**Missions Completed:** {_format_number(missions_completed)}")
    lines.append(f"**Resources Mined:** {_format_number(resources_mined)}")
    lines.append(f"**Alliance Helps Sent:** {_format_number(alliance_helps_sent)}")
    lines.append(
        "**Power gained since last join:** "
        f"{_format_number(power_since_join)}"
    )
    lines.append(f"**Power gained today:** {_format_number(power_today)}")
    lines.append(f"**Power gained last 7 days:** {_format_number(power_7)}")
    lines.append(f"**Power gained last 30 days:** {_format_number(power_30)}")
    lines.append(f"**Original Join:** {_format_join_date(member.original_join_date)}")
    lines.append(f"**Last Join:** {_format_join_date(member.last_join_date)}")
    if getattr(member, "previous_names", None):
        lines.append(f"**Previous Names:** {', '.join(member.previous_names)}")
    lines.append("")

    events = list(getattr(member, "service_events", []) or [])
    if not events:
        lines.append("No recorded events yet.")

    totals = contributions_total or {"helps": 0, "rss": 0, "iso": 0, "resources_mined": 0}
    last_30 = contributions_30 or {"helps": 0, "rss": 0, "iso": 0, "resources_mined": 0}
    last_7 = contributions_7 or {"helps": 0, "rss": 0, "iso": 0, "resources_mined": 0}
    last_1 = contributions_1 or {"helps": 0, "rss": 0, "iso": 0, "resources_mined": 0}

    lines.append("")
    lines.append("**Contributions:**")
    column_specs = [
        {"key": "period", "label": "Period", "min_width": 16},
        {"key": "helps", "label": "Helps", "min_width": 5},
        {"key": "rss", "label": "RSS", "min_width": 7},
        {"key": "iso", "label": "ISO", "min_width": 5},
        {"key": "resources_mined", "label": "Mined", "min_width": 7},
    ]
    contributions_table = build_table_from_rows(
        column_specs,
        [
            _format_contribution_row("Since last join", totals),
            _format_contribution_row("Last 30 days", last_30),
            _format_contribution_row("Last 7 days", last_7),
            _format_contribution_row("Last day", last_1),
        ],
    )
    lines.extend(["```", contributions_table, "```"])

    if not events:
        return "\n".join(lines)

    # Sort by timestamp if present
    events.sort(key=lambda e: e.get("timestamp", ""))

    lines.append("**Events:**")
    for ev in events:
        etype = ev.get("type", "")
        ts = _format_timestamp(ev.get("timestamp"))
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
        elif etype == "level_up":
            desc = f"Leveled up from {ev.get('old_level')} to {ev.get('new_level')}"
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
        sub_options = sub.get("options") or []
        for opt in sub_options:
            if opt.get("name") == "period" and opt.get("value") in _REPORT_VALUES:
                return opt["value"]
        if sub_name in _REPORT_BY_SUBCOMMAND:
            return _REPORT_BY_SUBCOMMAND[sub_name]
    for opt in options:
        if opt.get("name") == "period" and opt.get("value") in _REPORT_VALUES:
            return opt["value"]
    return fallback


def _get_subcommand_option(payload: dict, option_name: str):
    data = payload.get("data", {})
    options = data.get("options") or []
    if options:
        sub = options[0]
        for opt in sub.get("options") or []:
            if opt.get("name") == option_name:
                return opt.get("value")
    for opt in options:
        if opt.get("name") == option_name:
            return opt.get("value")
    return None


def handle_report_slash(payload: dict, period: ReportPeriod):
    """
    Thin adapter for slash commands.
    No business logic lives here.
    """
    guild_id = payload.get("guild_id")
    resolved_period = _resolve_report_period(payload, period)
    player_name = _get_subcommand_option(payload, "player")
    log.info(
        "Slash report requested: guild=%s period=%s",
        guild_id,
        resolved_period,
    )
    reports = build_service_reports(
        resolved_period,
        guild_id=guild_id,
        player_name=player_name,
    )
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
