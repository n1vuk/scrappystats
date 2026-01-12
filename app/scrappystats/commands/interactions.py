
"""High-level interaction helpers for Discord commands (v2.0.0).

These functions are intentionally independent of FastAPI / HTTP details.
They operate purely on alliance_id / member_name and return formatted text
using the v2 state layer and slash command formatters.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from typing import Optional

from ..storage.state import (
    load_state,
    record_pull_history,
    get_guild_name_overrides,
)
from ..models.member import Member
from .slash_fullroster import full_roster_messages
from .slash_service import service_record_command
from ..discord_utils import interaction_response, send_followup_message
# refactor allience load to new function
# from ..config import load_config
from scrappystats.config import load_config, get_guild_alliances
#config = load_alliances()

from ..services.fetch import fetch_alliance_roster, scrape_timestamp
from ..services.sync import run_alliance_sync
from ..services.test_mode import (
    format_test_mode_webhook,
    is_test_mode_enabled,
    load_test_roster,
)
from ..utils import (
    load_json,
    state_path as report_state_path,
)
from ..webhook.sender import post_webhook_message
from ..services.report_common import (
    compute_deltas,
    load_snapshot_at_or_after,
    load_snapshot_at_or_before,
)


log = logging.getLogger("scrappystats.forcepull")

def _format_pull_timestamp(raw: str | None) -> str:
    if not raw:
        return "Unknown time"
    value = str(raw)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        return parsed.strftime("%b %d, %Y %H:%M UTC")
    except ValueError:
        return value

def _send_followups_async(
    app_id: Optional[str],
    token: Optional[str],
    messages: list[str],
    ephemeral: bool = True,
) -> None:
    if not messages:
        return

    def _send():
        time.sleep(0.25)
        for message in messages:
            send_followup_message(app_id, token, message, ephemeral=ephemeral)

    threading.Thread(target=_send, daemon=True).start()

def _resolve_alliance(config: dict, guild_id: str) -> Optional[dict]:
    alliances = get_guild_alliances(config, guild_id)

    if len(alliances) == 1:
        log.info(
            "Defaulting to the only configured alliance for guild %s",
            guild_id,
        )
        return alliances[0]

    return None


def _resolve_alliances(config: dict, guild_id: str) -> list[dict]:
    alliances = get_guild_alliances(config, guild_id)
    if alliances:
        return alliances

    guilds = config.get("guilds") or []
    if guilds:
        return []

    return config.get("alliances", []) or []


def handle_player_autocomplete(payload: dict, query: str) -> list[dict]:
    guild_id = payload.get("guild_id") or "default"
    alliance = _resolve_alliance(load_config(), guild_id)
    if not alliance:
        return []
    state = load_state(alliance.get("id", guild_id))
    overrides = get_guild_name_overrides(state, guild_id)
    members_raw = (state.get("members") or {}).values()
    names = []
    for data in members_raw:
        member = Member.from_json(data)
        display_name = overrides.get(member.uuid, member.name)
        if display_name:
            names.append(display_name)
    names = sorted(set(names), key=str.lower)
    if query:
        needle = query.lower()
        names = [name for name in names if needle in name.lower()]
    return [{"name": name, "value": name} for name in names[:25]]

def _run_forcepull(guild_id: str):
    alliance_id = None
    pull_timestamp = None
    try:
        config = load_config()
        alliances = _resolve_alliances(config, guild_id)
        if not alliances:
            log.error("Forcepull failed for guild %s: no alliances configured", guild_id)
            return

        debug = bool(config.get("debug"))
        pull_timestamp = scrape_timestamp()
        log.info("Forcepull started for guild %s (%s alliances)", guild_id, len(alliances))

        for alliance in alliances:
            alliance_id = alliance.get("id")
            if not alliance_id:
                log.error("Forcepull skipped for guild %s: alliance missing id", guild_id)
                continue

            try:
                if is_test_mode_enabled(alliance):
                    test_payload = load_test_roster(alliance_id)
                    if not test_payload:
                        record_pull_history(alliance_id, pull_timestamp, False, source="test")
                        log.error(
                            "Forcepull failed: no test data available for alliance %s",
                            alliance_id,
                        )
                        continue
                    roster, test_timestamp, test_message, test_file = test_payload
                    source = "test"
                    log.info(
                        "Forcepull test mode using %s members at %s for alliance %s.",
                        len(roster),
                        test_timestamp,
                        alliance_id,
                    )
                    post_webhook_message(
                        format_test_mode_webhook(test_file, test_message),
                        alliance_id=alliance_id,
                    )
                    payload = {
                        "id": alliance_id,
                        "alliance_name": alliance.get("alliance_name") or alliance.get("name"),
                        "scraped_members": roster,
                        "scrape_timestamp": test_timestamp,
                    }
                else:
                    roster = fetch_alliance_roster(
                        alliance_id,
                        debug=debug,
                        scrape_stamp=pull_timestamp,
                    )
                    source = "forcepull"
                    payload = {
                        "id": alliance_id,
                        "alliance_name": alliance.get("alliance_name") or alliance.get("name"),
                        "scraped_members": roster,
                        "scrape_timestamp": pull_timestamp,
                    }

                # This function must be the SAME one cron/startup uses.
                data_changed = run_alliance_sync(payload)
                record_pull_history(
                    alliance_id,
                    payload["scrape_timestamp"],
                    True,
                    source=source,
                    data_changed=data_changed,
                )
            except Exception:
                log.exception("Forcepull failed for alliance %s (guild %s)", alliance_id, guild_id)
                record_pull_history(
                    alliance_id,
                    pull_timestamp or scrape_timestamp(),
                    False,
                    source="test" if alliance and is_test_mode_enabled(alliance) else "forcepull",
                )

        log.info("Forcepull completed for guild %s", guild_id)

    except Exception:
        log.exception("Forcepull failed for guild %s", guild_id)
        if alliance_id:
            record_pull_history(alliance_id, pull_timestamp or scrape_timestamp(), False, source="forcepull")
        
def handle_forcepull(payload: dict):
    guild_id = payload.get("guild_id")

    if not guild_id:
        return interaction_response(
            "❌ Force pull must be run from a server.",
            ephemeral=True,
        )

    threading.Thread(
        target=_run_forcepull,
        args=(guild_id,),
        daemon=True,
    ).start()

    return interaction_response(
        "🛠 **Force pull started**\nScrappy is fetching and syncing alliance data.",
        ephemeral=True,
    )


def handle_fullroster(payload: dict) -> dict:
    """Return a formatted full roster response for the given guild."""
    guild_id = payload.get("guild_id") or "default"
    alliance = _resolve_alliance(load_config(), guild_id)
    if not alliance:
        return interaction_response(
            "❌ Full roster failed: no alliance configured for this server.",
            ephemeral=True,
        )
    state = load_state(alliance.get("id", guild_id))
    overrides = get_guild_name_overrides(state, guild_id)
    service_state = _load_service_state(alliance.get("id", guild_id))
    active_names = set(service_state.keys())
    messages = full_roster_messages(
        state,
        service_state=service_state,
        name_overrides=overrides,
        active_names=active_names,
    )
    primary = messages[0]
    if len(messages) > 1:
        app_id = payload.get("application_id")
        token = payload.get("token")
        _send_followups_async(app_id, token, messages[1:], ephemeral=True)
    return interaction_response(primary, ephemeral=True)


def _find_member_by_name(
    state: dict,
    name: str,
    *,
    guild_id: Optional[str] = None,
) -> Optional[Member]:
    """Find a Member by (case-insensitive) exact name match.

    Returns the first Member instance with matching name, or None if not found.
    """
    target = name.lower()
    guild_overrides = get_guild_name_overrides(state, guild_id)
    members_raw = (state.get("members") or {}).values()
    for data in members_raw:
        m = Member.from_json(data)
        if m.name.lower() == target:
            return m
        if any(prev.lower() == target for prev in (m.previous_names or [])):
            return m
        override = guild_overrides.get(m.uuid, "")
        if override and override.lower() == target:
            return m
    return None


def _display_member_name(member: Member, guild_overrides: dict) -> str:
    return guild_overrides.get(member.uuid, member.name)


def _load_service_state(alliance_id: str) -> dict:
    return load_json(report_state_path(alliance_id), {})


def _member_contributions_since(
    alliance_id: str,
    member_name: str,
    *,
    days: int,
) -> dict:
    now = datetime.now(timezone.utc)
    end_snapshot = load_snapshot_at_or_before(alliance_id, now)
    current = end_snapshot or _load_service_state(alliance_id)
    start_dt = now - timedelta(days=days)
    start_snapshot = load_snapshot_at_or_before(alliance_id, start_dt)
    if not start_snapshot:
        start_snapshot = load_snapshot_at_or_after(alliance_id, start_dt)
    previous = start_snapshot or current
    deltas = compute_deltas(current, previous)
    return deltas.get(
        member_name,
        {"helps": 0, "rss": 0, "iso": 0, "resources_mined": 0},
    )


def _member_total_contributions(alliance_id: str, member_name: str) -> dict:
    service_state = _load_service_state(alliance_id)
    return service_state.get(
        member_name,
        {"helps": 0, "rss": 0, "iso": 0, "resources_mined": 0},
    )

def _parse_report_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    value = str(raw).strip().replace(" ", "T")
    if value.endswith("Z") and "+" in value:
        value = value[:-1]
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = datetime.fromisoformat(value)
            parsed = parsed_date.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _member_stat_at_or_before(
    alliance_id: str,
    member_name: str,
    target_dt: datetime,
) -> dict:
    snapshot = load_snapshot_at_or_before(alliance_id, target_dt)
    if not snapshot:
        return {}
    return snapshot.get(member_name, {}) or {}

def _stat_gain(current: int, baseline: int | None) -> int:
    if baseline is None:
        return 0
    return max(current - int(baseline or 0), 0)


def handle_service_record(
    alliance_id: str,
    player_name: str,
    *,
    guild_id: Optional[str] = None,
    alliance_name: Optional[str] = None,
) -> str:
    """Return a formatted service record for the given player name.

    If the member is not found, returns a friendly error string rather than raising.
    """
    state = load_state(alliance_id)
    member = _find_member_by_name(state, player_name, guild_id=guild_id)
    if not member:
        return f"Scrappy tilts his head — I can't find any officer named '{player_name}', Captain."
    contributions_total = _member_total_contributions(alliance_id, member.name)
    contributions_30 = _member_contributions_since(alliance_id, member.name, days=30)
    contributions_7 = _member_contributions_since(alliance_id, member.name, days=7)
    contributions_1 = _member_contributions_since(alliance_id, member.name, days=1)
    service_state = _load_service_state(alliance_id)
    is_active_member = member.name in service_state
    member_state = service_state.get(member.name, {}) or {}
    current_power = int(member_state.get("power", member.power) or 0)
    max_power = int(member_state.get("max_power", current_power) or 0)
    power_destroyed = int(member_state.get("power_destroyed", 0) or 0)
    arena_rating = int(member_state.get("arena_rating", 0) or 0)
    assessment_rank = int(member_state.get("assessment_rank", 0) or 0)
    missions_completed = int(member_state.get("missions_completed", 0) or 0)
    resources_mined = int(member_state.get("resources_mined", 0) or 0)
    alliance_helps_sent = int(member_state.get("alliance_helps_sent", 0) or 0)

    now = datetime.now(timezone.utc)
    start_of_today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    stats_today = _member_stat_at_or_before(alliance_id, member.name, start_of_today)
    stats_7 = _member_stat_at_or_before(alliance_id, member.name, now - timedelta(days=7))
    stats_30 = _member_stat_at_or_before(alliance_id, member.name, now - timedelta(days=30))
    last_join_dt = _parse_report_timestamp(member.last_join_date)
    power_since_join = (
        _member_stat_at_or_before(alliance_id, member.name, last_join_dt).get("power")
        if last_join_dt
        else None
    )

    overrides = get_guild_name_overrides(state, guild_id)
    display_name = _display_member_name(member, overrides)
    if display_name != member.name:
        member = Member.from_json(member.to_json())
        member.name = display_name
    message = service_record_command(
        member,
        power=max_power or current_power,
        max_power=max_power,
        power_destroyed=power_destroyed,
        arena_rating=arena_rating,
        assessment_rank=assessment_rank,
        missions_completed=missions_completed,
        resources_mined=resources_mined,
        alliance_helps_sent=alliance_helps_sent,
        power_since_join=_stat_gain(current_power, power_since_join),
        power_today=_stat_gain(current_power, stats_today.get("power")),
        power_7=_stat_gain(current_power, stats_7.get("power")),
        power_30=_stat_gain(current_power, stats_30.get("power")),
        contributions_total=contributions_total,
        contributions_30=contributions_30,
        contributions_7=contributions_7,
        contributions_1=contributions_1,
    )
    if not is_active_member:
        alliance_label = (alliance_name or "THIS ALLIANCE").upper()
        return f"NO LONGER A MEMBER OF {alliance_label}\n{message}"
    return message


def _get_subcommand_option(payload: dict, option_name: str) -> Optional[str]:
    data = payload.get("data", {})
    options = data.get("options") or []
    if not options:
        return None
    sub = options[0]
    for opt in sub.get("options") or []:
        if opt.get("name") == option_name:
            return opt.get("value")
    return None


def handle_service_record_slash(payload: dict) -> dict:
    guild_id = payload.get("guild_id") or "default"
    alliance = _resolve_alliance(load_config(), guild_id)
    if not alliance:
        return interaction_response(
            "❌ Service record failed: no alliance configured for this server.",
            ephemeral=True,
        )
    player_name = _get_subcommand_option(payload, "player")
    if not player_name:
        return interaction_response(
            "❌ Service record failed: provide a player name.",
            ephemeral=True,
        )
    alliance_id = alliance.get("id", guild_id)
    message = handle_service_record(
        alliance_id,
        player_name,
        guild_id=guild_id,
        alliance_name=alliance.get("alliance_name") or alliance.get("name"),
    )
    return interaction_response(message, ephemeral=True)


def _chunk_lines(lines: list[str], limit: int = 1900) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line)
        extra = line_len + (1 if current else 0)
        if current and current_len + extra > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
            continue
        current.append(line)
        current_len += extra
    if current:
        chunks.append("\n".join(current))
    return chunks


def _member_name_change_lines(member: Member) -> list[str]:
    lines = [f"🗂 **Name changes for {member.name}**"]
    rename_events = [
        ev for ev in (member.service_events or []) if ev.get("type") == "rename"
    ]
    if rename_events:
        rename_events.sort(key=lambda ev: ev.get("timestamp", ""))
        for ev in rename_events:
            ts = ev.get("timestamp", "")
            old_name = ev.get("old_name", "Unknown")
            new_name = ev.get("new_name", member.name)
            lines.append(f"- {ts} — {old_name} → **{new_name}**")
    elif member.previous_names:
        lines.append(f"Previous names: {', '.join(member.previous_names)}")
    else:
        lines.append("No recorded name changes.")
    return lines


def _collect_name_change_members(state: dict) -> list[Member]:
    members: list[Member] = []
    for data in (state.get("members") or {}).values():
        member = Member.from_json(data)
        if member.previous_names or any(
            ev.get("type") == "rename" for ev in (member.service_events or [])
        ):
            members.append(member)
    members.sort(key=lambda m: m.name.lower())
    return members


def handle_name_changes_slash(payload: dict) -> dict:
    guild_id = payload.get("guild_id") or "default"
    alliance = _resolve_alliance(load_config(), guild_id)
    if not alliance:
        return interaction_response(
            "❌ Name change lookup failed: no alliance configured for this server.",
            ephemeral=True,
        )
    state = load_state(alliance.get("id", guild_id))
    player_name = _get_subcommand_option(payload, "player")
    if player_name:
        member = _find_member_by_name(state, player_name)
        if not member:
            return interaction_response(
                f"Scrappy tilts his head — I can't find any officer named '{player_name}', Captain.",
                ephemeral=True,
            )
        lines = _member_name_change_lines(member)
        return interaction_response("\n".join(lines), ephemeral=True)

    members = _collect_name_change_members(state)
    if not members:
        return interaction_response(
            "🗂 No recorded name changes in the current roster.",
            ephemeral=True,
        )

    lines = ["🗂 **Recorded name changes**"]
    for member in members:
        previous = ", ".join(member.previous_names) or "Unknown"
        lines.append(f"- {member.name} (was {previous})")

    chunks = _chunk_lines(lines)
    primary = chunks[0]
    if len(chunks) > 1:
        app_id = payload.get("application_id")
        token = payload.get("token")
        _send_followups_async(app_id, token, chunks[1:], ephemeral=True)

    return interaction_response(primary, ephemeral=True)


def handle_pull_history_slash(payload: dict) -> dict:
    guild_id = payload.get("guild_id") or "default"
    alliance = _resolve_alliance(load_config(), guild_id)
    if not alliance:
        return interaction_response(
            "❌ Pull history lookup failed: no alliance configured for this server.",
            ephemeral=True,
        )
    state = load_state(alliance.get("id", guild_id))
    history = list(state.get("pull_history") or [])
    if not history:
        return interaction_response(
            "🧭 No pull history recorded yet.",
            ephemeral=True,
        )
    recent = history[-5:]
    lines = ["🧭 **Last 5 pulls**"]
    for entry in recent:
        ts = _format_pull_timestamp(entry.get("timestamp"))
        status = "✅ Success" if entry.get("success") else "❌ Failed"
        source = entry.get("source")
        suffix = f" ({source})" if source else ""
        data_changed = entry.get("data_changed")
        data_suffix = ""
        if data_changed is True:
            data_suffix = " • data changed"
        elif data_changed is False:
            data_suffix = " • no data change"
        lines.append(f"- {ts} — {status}{suffix}{data_suffix}")
    return interaction_response("\n".join(lines), ephemeral=True)
