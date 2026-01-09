
import json
import os
import uuid
from typing import Optional

from .files import ensure_data_dir, state_path
from ..models.member import Member
from ..utils import iso_now

def load_state(alliance_id: str) -> dict:
    """Load JSON state for the given alliance_id.

    Returns a dict with keys:
      - alliance_id
      - last_sync
      - members: {uuid: member_json}
      - pull_history: list[dict]
    """
    path = state_path(alliance_id)
    if not os.path.exists(path):
        return {
            "alliance_id": alliance_id,
            "last_sync": None,
            "members": {},
            "pull_history": [],
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(alliance_id: str, state: dict) -> None:
    """Persist state to disk for the given alliance_id."""
    ensure_data_dir()
    path = state_path(alliance_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def record_pull_history(
    alliance_id: str,
    timestamp: Optional[str],
    success: bool,
    source: Optional[str] = None,
    data_changed: Optional[bool] = None,
) -> None:
    """Record a pull attempt for the given alliance."""
    state = load_state(alliance_id)
    history = state.get("pull_history") or []
    entry = {
        "timestamp": timestamp or iso_now(),
        "success": bool(success),
    }
    if source:
        entry["source"] = source
    if data_changed is not None:
        entry["data_changed"] = bool(data_changed)
    history.append(entry)
    state["pull_history"] = history[-20:]
    save_state(alliance_id, state)

def initialize_member(scraped: dict, scrape_timestamp: str) -> dict:
    """Create an initial serialized Member for a newly-seen player.

    STFC.pro provides a join_date as YYYY-MM-DD (most recent join).
    We combine that date with the scrape_timestamp's time-of-day to form an
    ISO-like timestamp for both original_join_date and last_join_date.
    """
    join_date = scraped.get("join_date")
    if not join_date:
        # Fallback: use the date portion of the scrape timestamp
        join_date = scrape_timestamp.split("T")[0]
    # Extract time portion from scrape_timestamp (or default)
    if "T" in scrape_timestamp:
        time_part = scrape_timestamp.split("T", 1)[1]
    else:
        time_part = "00:00:00Z"
    combined_ts = f"{join_date}T{time_part}"

    m = Member(
        uuid=str(uuid.uuid4()),
        name=scraped["name"],
        level=scraped.get("level", 0),
        rank=scraped.get("rank", "Unknown"),
        original_join_date=combined_ts,
        last_join_date=combined_ts,
    )
    return m.to_json()
