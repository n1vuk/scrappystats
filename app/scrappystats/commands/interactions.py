
"""High-level interaction helpers for Discord commands (v2.0.0).

These functions are intentionally independent of FastAPI / HTTP details.
They operate purely on alliance_id / member_name and return formatted text
using the v2 state layer and slash command formatters.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from pathlib import Path
from typing import Optional

from ..storage.state import (
    load_state,
    record_pull_history,
    save_state,
    get_guild_name_overrides,
    set_guild_name_override,
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
from ..services.service_record import add_service_event
from ..utils import (
    load_json,
    save_json,
    state_path as report_state_path,
    PENDING_RENAMES_DIR,
)
from ..webhook.sender import post_webhook_message
from ..services.report_common import compute_deltas, load_snapshot_at_or_before


log = logging.getLogger("scrappystats.forcepull")

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
                    roster = fetch_alliance_roster(alliance_id, debug=debug)
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


def _find_member_record(state: dict, name: str) -> tuple[Optional[str], Optional[Member]]:
    target = name.lower()
    members_raw = (state.get("members") or {}).items()
    for uid, data in members_raw:
        member = Member.from_json(data)
        if member.name.lower() == target:
            return uid, member
    return None, None


def _find_member_record_any_name(
    state: dict,
    name: str,
    *,
    guild_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[Member]]:
    target = name.lower()
    guild_overrides = get_guild_name_overrides(state, guild_id)
    members_raw = (state.get("members") or {}).items()
    for uid, data in members_raw:
        member = Member.from_json(data)
        if member.name.lower() == target:
            return uid, member
        if any(prev.lower() == target for prev in (member.previous_names or [])):
            return uid, member
        override = guild_overrides.get(member.uuid, "")
        if override and override.lower() == target:
            return uid, member
    return None, None


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
    previous = start_snapshot or current
    deltas = compute_deltas(current, previous)
    return deltas.get(member_name, {"helps": 0, "rss": 0, "iso": 0})


def _member_total_contributions(alliance_id: str, member_name: str) -> dict:
    service_state = _load_service_state(alliance_id)
    return service_state.get(member_name, {"helps": 0, "rss": 0, "iso": 0})


def handle_service_record(
    alliance_id: str,
    player_name: str,
    *,
    guild_id: Optional[str] = None,
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

    overrides = get_guild_name_overrides(state, guild_id)
    display_name = _display_member_name(member, overrides)
    if display_name != member.name:
        member = Member.from_json(member.to_json())
        member.name = display_name
    return service_record_command(
        member,
        power=member.power,
        contributions_total=contributions_total,
        contributions_30=contributions_30,
        contributions_7=contributions_7,
        contributions_1=contributions_1,
    )


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
    message = handle_service_record(alliance_id, player_name, guild_id=guild_id)
    return interaction_response(message, ephemeral=True)


def _pending_rename_files(alliance_id: str) -> list[Path]:
    return sorted(PENDING_RENAMES_DIR.glob(f"{alliance_id}_*.json"))


def _load_pending_renames(alliance_id: str) -> list[dict]:
    pending: list[dict] = []
    for path in _pending_rename_files(alliance_id):
        records = load_json(path, [])
        for idx, record in enumerate(records):
            pending.append(
                {
                    "path": path,
                    "index": idx,
                    "record": record,
                }
            )
    return pending


def _update_pending_file(path: Path, records: list[dict]) -> None:
    if not records:
        if path.exists():
            path.unlink()
        return
    save_json(path, records)


def _apply_manual_rename(alliance_id: str, old_name: str, new_name: str) -> str:
    state = load_state(alliance_id)
    old_uid, old_member = _find_member_record(state, old_name)
    new_uid, new_member = _find_member_record(state, new_name)

    if not old_member:
        return f"❌ Could not find an officer named '{old_name}'."
    if not new_member:
        return f"❌ Could not find an officer named '{new_name}'."
    if old_uid == new_uid:
        return "⚠️ These names already refer to the same officer."

    if old_member.name not in old_member.previous_names:
        old_member.previous_names.append(old_member.name)
    if new_member.name not in old_member.previous_names:
        old_member.previous_names.append(new_member.name)
    old_member.name = new_member.name
    old_member.rank = new_member.rank
    old_member.level = new_member.level
    old_member.service_events.extend(new_member.service_events or [])
    add_service_event(old_member, "rename", old_name=old_name, new_name=new_name)

    members = state.get("members") or {}
    members[old_uid] = old_member.to_json()
    if new_uid in members:
        del members[new_uid]
    state["members"] = members
    save_state(alliance_id, state)
    return f"✅ Updated {old_name} to **{new_name}** and merged records."


def _apply_guild_name_override(
    alliance_id: str,
    guild_id: str,
    target_name: str,
    override_name: str,
) -> str:
    state = load_state(alliance_id)
    member_id, member = _find_member_record_any_name(state, target_name, guild_id=guild_id)
    if not member or not member_id:
        return f"❌ Could not find an officer named '{target_name}'."
    override_name = override_name.strip()
    if not override_name:
        return "❌ Override name cannot be empty."

    overrides = get_guild_name_overrides(state, guild_id)
    if override_name == member.name:
        if member_id in overrides:
            set_guild_name_override(state, guild_id=guild_id, member_uuid=member_id, display_name=None)
            save_state(alliance_id, state)
            return f"✅ Cleared guild name override for **{member.name}**."
        return f"⚠️ No guild override set for **{member.name}**."

    set_guild_name_override(state, guild_id=guild_id, member_uuid=member_id, display_name=override_name)
    save_state(alliance_id, state)
    return f"✅ Set guild name override: {member.name} → **{override_name}**."


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


def handle_rename_review_slash(payload: dict) -> dict:
    guild_id = payload.get("guild_id") or "default"
    alliance = _resolve_alliance(load_config(), guild_id)
    if not alliance:
        return interaction_response(
            "❌ Rename review failed: no alliance configured for this server.",
            ephemeral=True,
        )
    alliance_id = alliance.get("id", guild_id)
    action = (_get_subcommand_option(payload, "action") or "list").lower()
    old_name = _get_subcommand_option(payload, "old_name")
    new_name = _get_subcommand_option(payload, "new_name")

    pending = _load_pending_renames(alliance_id)
    if action == "list":
        if not pending:
            return interaction_response(
                "🛟 No pending rename reviews found.",
                ephemeral=True,
            )
        lines = ["🛟 **Pending rename reviews**"]
        for item in pending:
            record = item["record"]
            old = record.get("old_name", "Unknown")
            new = record.get("new_name", "Unknown")
            reason = record.get("reason", "manual_review")
            notes = ", ".join(record.get("notes", [])) or record.get("notes") or "no metrics"
            lines.append(f"- {old} → **{new}** ({reason}; {notes})")
        chunks = _chunk_lines(lines)
        primary = chunks[0]
        if len(chunks) > 1:
            app_id = payload.get("application_id")
            token = payload.get("token")
            _send_followups_async(app_id, token, chunks[1:], ephemeral=True)
        return interaction_response(primary, ephemeral=True)

    if action not in {"approve", "decline"}:
        return interaction_response(
            "❌ Invalid action. Use `list`, `approve`, or `decline`.",
            ephemeral=True,
        )
    if not old_name or not new_name:
        return interaction_response(
            "❌ Provide both old_name and new_name for approve/decline.",
            ephemeral=True,
        )

    matched = None
    for item in pending:
        record = item["record"]
        if (
            str(record.get("old_name", "")).lower() == old_name.lower()
            and str(record.get("new_name", "")).lower() == new_name.lower()
        ):
            matched = item
            break

    if not matched:
        return interaction_response(
            "⚠️ No pending rename review found for that pair.",
            ephemeral=True,
        )

    if action == "approve":
        result = _apply_manual_rename(alliance_id, old_name, new_name)
        if not result.startswith("✅"):
            return interaction_response(result, ephemeral=True)
    else:
        result = f"🗑️ Declined pending rename: {old_name} → {new_name}."

    path = matched["path"]
    records = load_json(path, [])
    index = matched["index"]
    if 0 <= index < len(records):
        records.pop(index)
    _update_pending_file(path, records)
    return interaction_response(result, ephemeral=True)


def handle_manual_rename_slash(payload: dict) -> dict:
    guild_id = payload.get("guild_id") or "default"
    alliance = _resolve_alliance(load_config(), guild_id)
    if not alliance:
        return interaction_response(
            "❌ Manual rename failed: no alliance configured for this server.",
            ephemeral=True,
        )
    old_name = _get_subcommand_option(payload, "old_name")
    new_name = _get_subcommand_option(payload, "new_name")
    if not old_name or not new_name:
        return interaction_response(
            "❌ Provide both old_name and new_name.",
            ephemeral=True,
        )
    alliance_id = alliance.get("id", guild_id)
    message = _apply_guild_name_override(alliance_id, guild_id, old_name, new_name)
    return interaction_response(message, ephemeral=True)


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
    for entry in reversed(recent):
        ts = entry.get("timestamp", "Unknown time")
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
