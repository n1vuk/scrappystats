
import json
import os
import uuid
from .files import ensure_data_dir, state_path
from ..models.member import Member

def load_state(alliance_id: str) -> dict:
    """Load JSON state for the given alliance_id.

    Returns a dict with keys:
      - alliance_id
      - last_sync
      - members: {uuid: member_json}
    """
    path = state_path(alliance_id)
    if not os.path.exists(path):
        return {
            "alliance_id": alliance_id,
            "last_sync": None,
            "members": {},
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(alliance_id: str, state: dict) -> None:
    """Persist state to disk for the given alliance_id."""
    ensure_data_dir()
    path = state_path(alliance_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)

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
