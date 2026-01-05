
"""High-level interaction helpers for Discord commands (v2.0.0).

These functions are intentionally independent of FastAPI / HTTP details.
They operate purely on alliance_id / member_name and return formatted text
using the v2 state layer and slash command formatters.
"""
import logging
import threading

from typing import Optional

from ..storage.state import load_state
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


log = logging.getLogger("scrappystats.forcepull")

def _resolve_alliance(config: dict, guild_id: str) -> Optional[dict]:
    alliances = get_guild_alliances(config, guild_id)

    if len(alliances) == 1:
        log.info(
            "Defaulting to the only configured alliance for guild %s",
            guild_id,
        )
        return alliances[0]

    return None

def _run_forcepull(guild_id: str):
    try:
        config = load_config()
        alliance = _resolve_alliance(config, guild_id)
        if not alliance:
            log.error("Forcepull failed for guild %s: no alliance configured", guild_id)
            return

        alliance_id = alliance.get("id")
        if not alliance_id:
            log.error("Forcepull failed for guild %s: alliance missing id", guild_id)
            return

        log.info("Forcepull started for guild %s", guild_id)

        debug = bool(config.get("debug"))
        roster = fetch_alliance_roster(alliance_id, debug=debug)
        payload = {
            "id": alliance_id,
            "alliance_name": alliance.get("alliance_name") or alliance.get("name"),
            "scraped_members": roster,
            "scrape_timestamp": scrape_timestamp(),
        }

        # This function must be the SAME one cron/startup uses.
        run_alliance_sync(payload)

        log.info("Forcepull completed for guild %s", guild_id)

    except Exception:
        log.exception("Forcepull failed for guild %s", guild_id)
        
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
    messages = full_roster_messages(state)
    primary = messages[0]
    if len(messages) > 1:
        app_id = payload.get("application_id")
        token = payload.get("token")
        for followup in messages[1:]:
            send_followup_message(app_id, token, followup, ephemeral=True)
    return interaction_response(primary, ephemeral=True)


def _find_member_by_name(state: dict, name: str) -> Optional[Member]:
    """Find a Member by (case-insensitive) exact name match.

    Returns the first Member instance with matching name, or None if not found.
    """
    target = name.lower()
    members_raw = (state.get("members") or {}).values()
    for data in members_raw:
        m = Member.from_json(data)
        if m.name.lower() == target:
            return m
        if any(prev.lower() == target for prev in (m.previous_names or [])):
            return m
    return None


def handle_service_record(alliance_id: str, player_name: str) -> str:
    """Return a formatted service record for the given player name.

    If the member is not found, returns a friendly error string rather than raising.
    """
    state = load_state(alliance_id)
    member = _find_member_by_name(state, player_name)
    if not member:
        return f"Scrappy tilts his head — I can't find any officer named '{player_name}', Captain."
    return service_record_command(member)


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
    message = handle_service_record(alliance_id, player_name)
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
        for followup in chunks[1:]:
            send_followup_message(app_id, token, followup, ephemeral=True)

    return interaction_response(primary, ephemeral=True)
