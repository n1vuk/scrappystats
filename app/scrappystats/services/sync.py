
"""Sync orchestrator for v2.0.0-dev with clean state, UUIDs, detection,
service-history, and webhook dispatch wired in."""
from datetime import datetime
from typing import Dict, List

from ..storage.state import load_state, save_state, initialize_member
from ..models.member import Member
from .detection import detect_member_events
from .service_record import add_service_event
from .events import dispatch_webhook_events


def _deserialize_members(raw_members: Dict[str, dict]) -> Dict[str, Member]:
    """Convert stored JSON dicts into Member objects keyed by UUID."""
    members: Dict[str, Member] = {}
    for uid, data in raw_members.items():
        m = Member.from_json(data)
        members[uid] = m
    return members


def _serialize_members(members: Dict[str, Member]) -> Dict[str, dict]:
    """Convert Member objects back into JSON-serializable dicts."""
    return {uid: m.to_json() for uid, m in members.items()}


def _detect_level_ups(previous: Dict[str, Member],
                      current: Dict[str, Member]) -> List[dict]:
    """Return list of level-up events.

    Each event is:
      {
        "member": Member,
        "old_level": int,
        "new_level": int,
      }
    """
    level_ups: List[dict] = []
    for uid, new in current.items():
        old = previous.get(uid)
        if not old:
            continue
        try:
            old_level = int(getattr(old, "level", 0) or 0)
            new_level = int(getattr(new, "level", 0) or 0)
        except (TypeError, ValueError):
            continue
        if new_level > old_level:
            level_ups.append(
                {
                    "member": new,
                    "old_level": old_level,
                    "new_level": new_level,
                }
            )
    return level_ups


def _detect_rejoins(previous: Dict[str, Member],
                    current: Dict[str, Member]) -> List[dict]:
    """Best-effort rejoin detection based on last service event.

    If a Member existed previously and their last recorded service_event
    is a 'leave', and they appear again in the current membership, we
    treat this as a rejoin.

    Each event is:
      {
        "member": Member,
        "last_leave": event_dict,
      }
    """
    rejoins: List[dict] = []
    for uid, new in current.items():
        old = previous.get(uid)
        if not old:
            continue
        events = list(getattr(old, "service_events", []) or [])
        if not events:
            continue
        last = events[-1]
        if last.get("type") == "leave":
            rejoins.append(
                {
                    "member": new,
                    "last_leave": last,
                }
            )
    return rejoins


def sync_alliance(alliance_cfg: dict) -> None:
    """Run a single sync for one alliance.

    alliance_cfg is expected to contain at least:
      - id: str                 (alliance identifier)
      - scrape_timestamp: str   (ISO string)
      - scraped_members: list[dict] with keys:
          - name: str
          - rank: str
          - level: int
          - join_date: 'YYYY-MM-DD' (from STFC.pro)
    """
    alliance_id = alliance_cfg.get("id", "default")
    state = load_state(alliance_id)

    scraped_members = alliance_cfg.get("scraped_members", [])
    scrape_timestamp = alliance_cfg.get("scrape_timestamp") or datetime.utcnow().isoformat() + "Z"

    # Deserialize previous members
    prev_raw = state.get("members", {}) or {}
    prev_members = _deserialize_members(prev_raw)

    # Build current members from scrape, matching by name where possible
    curr_members: Dict[str, Member] = {}

    for scraped in scraped_members:
        name = scraped["name"]
        # Try to find an existing member with this name
        match_uuid = None
        for uid, m in prev_members.items():
            if m.name == name:
                match_uuid = uid
                break

        if match_uuid:
            # Existing member: update fields in-place
            m = prev_members[match_uuid]
            m.name = scraped["name"]
            m.rank = scraped.get("rank", m.rank)
            m.level = scraped.get("level", m.level)
            # last_join_date remains unchanged here; we only bump it on explicit rejoin logic
            curr_members[match_uuid] = m
        else:
            # New member in v2: initialize from scrape
            m_json = initialize_member(scraped, scrape_timestamp)
            m = Member.from_json(m_json)
            curr_members[m.uuid] = m

    # Run detection on Member objects
    joins, leaves, renames, promotions, demotions = detect_member_events(prev_members, curr_members)

    # Additional event types derived here
    level_ups = _detect_level_ups(prev_members, curr_members)
    rejoins = _detect_rejoins(prev_members, curr_members)

    # Apply events to service records
    for m in joins:
        add_service_event(m, "join")

    for m in leaves:
        add_service_event(m, "leave")

    for r in renames:
        add_service_event(
            r["member"],
            "rename",
            old_name=r["old_name"],
            new_name=r["new_name"],
        )

    for p in promotions:
        add_service_event(
            p["member"],
            "promotion",
            old_rank=p["old_rank"],
            new_rank=p["new_rank"],
        )

    for d in demotions:
        add_service_event(
            d["member"],
            "demotion",
            old_rank=d["old_rank"],
            new_rank=d["new_rank"],
        )

    for ev in level_ups:
        add_service_event(
            ev["member"],
            "level_up",
            old_level=ev["old_level"],
            new_level=ev["new_level"],
        )

    for ev in rejoins:
        add_service_event(
            ev["member"],
            "rejoin",
            last_leave=ev["last_leave"],
        )

    # Prepare a flat list of events for webhook dispatch
    event_batch = []

    for m in joins:
        event_batch.append({"type": "join", "member": m})
    for m in leaves:
        event_batch.append({"type": "leave", "member": m})
    for r in renames:
        event_batch.append(
            {
                "type": "rename",
                "member": r["member"],
                "old_name": r["old_name"],
                "new_name": r["new_name"],
            }
        )
    for p in promotions:
        event_batch.append(
            {
                "type": "promotion",
                "member": p["member"],
                "old_rank": p["old_rank"],
                "new_rank": p["new_rank"],
            }
        )
    for d in demotions:
        event_batch.append(
            {
                "type": "demotion",
                "member": d["member"],
                "old_rank": d["old_rank"],
                "new_rank": d["new_rank"],
            }
        )
    for ev in level_ups:
        event_batch.append(
            {
                "type": "level_up",
                "member": ev["member"],
                "old_level": ev["old_level"],
                "new_level": ev["new_level"],
            }
        )
    for ev in rejoins:
        event_batch.append(
            {
                "type": "rejoin",
                "member": ev["member"],
                "last_leave": ev["last_leave"],
            }
        )

    # Dispatch webhook messages for all events.
    try:
        dispatch_webhook_events(event_batch, scrape_timestamp)
    except Exception as exc:
        # Log but do not fail the sync.
        print(f"[sync_alliance] webhook dispatch failed: {exc}")

    # Merge previous and current members so leavers stay in the history
    final_members: Dict[str, Member] = dict(prev_members)
    final_members.update(curr_members)

    state["members"] = _serialize_members(final_members)
    state["last_sync"] = scrape_timestamp
    save_state(alliance_id, state)

# def run_alliance_sync(alliance: dict) -> None:
#     """
#     Canonical orchestration entry point for syncing an alliance.
#     Used by cron, startup, and forcepull.
#     """
#     cfg = build_alliance_cfg(alliance)
#     run_alliance_sync(alliance)

def run_alliance_sync(alliance: dict) -> None:
    """
    Canonical orchestration entry point.

    - Scrapes data
    - Builds alliance_cfg
    - Calls sync_alliance()

    Used by cron, startup, and forcepull.
    """
    alliance_id = alliance.get("id", "default")

    scraped_members = alliance.get("scraped_members", [])
    scrape_timestamp = alliance.get("scrape_timestamp") or (
        datetime.utcnow().isoformat() + "Z"
    )

    cfg = {
        "id": alliance_id,
        "scraped_members": scraped_members,
        "scrape_timestamp": scrape_timestamp,
    }

    sync_alliance(cfg)
    
def main():
    # Simple test harness; replace with real config/cron wiring.
    cfg = {
        "id": "test",
        "scrape_timestamp": "2025-02-10T21:14:00Z",
        "scraped_members": [
            {"name": "TestUser", "rank": "Agent", "level": 10, "join_date": "2025-02-10"},
            {"name": "AnotherUser", "rank": "Operative", "level": 12, "join_date": "2025-02-10"},
        ],
    }
    sync_alliance(cfg)


def run_all():
    return main()

