
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
from .slash_fullroster import full_roster_command
from .slash_service import service_record_command
from ..discord_utils import interaction_response
# refactor allience load to new function
# from ..config import load_config
from scrappystats.config_loader import load_alliances
#config = load_alliances()

from ..services.sync import run_alliance_sync


log = logging.getLogger("scrappystats.forcepull")

def _run_forcepull(guild_id: str):
    try:
        # #config = load_config()
        # config = load_alliances()
        # alliance = config.get("alliances", {}).get(guild_id)

        # if not alliance:
        #     log.warning("Forcepull: no alliance configured for guild %s", guild_id)
        #     return
        alliances = load_alliances()

        alliance = next(
            (a for a in alliances if a.get("id") == str(guild_id)),
            None
            )   
        if not alliance:
            log.error(f"Forcepull failed for guild {guild_id}")
   
        log.info("Forcepull started for guild %s", guild_id)

        # This function must be the SAME one cron/startup uses
        run_alliance_sync(alliance)

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
    state = load_state(guild_id)
    message = full_roster_command(state)
    return interaction_response(message, ephemeral=True)


def _find_member_by_name(state: dict, name: str) -> Optional[Member]:
    """Find a Member by (case-insensitive) exact name match.

    Returns the first Member instance with matching name, or None if not found.
    """
    members_raw = (state.get("members") or {}).values()
    for data in members_raw:
        m = Member.from_json(data)
        if m.name.lower() == name.lower():
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
