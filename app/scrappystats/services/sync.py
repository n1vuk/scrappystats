
"""Sync orchestrator for v2.0.0-dev with clean state, UUIDs, detection,
service-history, and webhook dispatch wired in."""
import logging
from datetime import datetime
from typing import Dict, List

from ..storage.state import load_state, save_state, initialize_member
from ..utils import (
    load_json,
    save_json,
    state_path as report_state_path,
    history_snapshot_path,
    append_event,
)
from ..models.member import Member
from .detection import detect_member_events
from .service_record import add_service_event
from .events import dispatch_webhook_events
from .member_details import queue_member_detail_refresh

log = logging.getLogger(__name__)


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

def _is_repeat_leave(member: Member) -> bool:
    events = list(getattr(member, "service_events", []) or [])
    if not events:
        return False
    return events[-1].get("type") == "leave"


def _combine_join_date(join_date: str | None, scrape_timestamp: str) -> str | None:
    if not join_date:
        return None
    if "T" in scrape_timestamp:
        time_part = scrape_timestamp.split("T", 1)[1]
    else:
        time_part = "00:00:00Z"
    return f"{join_date}T{time_part}"


def _clone_member(member: Member) -> Member:
    return Member.from_json(member.to_json())

def _scraped_value(scraped: dict, key: str, fallback):
    if key in scraped and scraped[key] is not None:
        return scraped[key]
    return fallback


def sync_alliance(alliance_cfg: dict) -> bool:
    """Run a single sync for one alliance.

    alliance_cfg is expected to contain at least:
      - id: str                 (alliance identifier)
      - scrape_timestamp: str   (ISO string)
      - alliance_name: str
      - scraped_members: list[dict] with keys:
          - name: str
          - rank: str
          - level: int
          - join_date: 'YYYY-MM-DD' (from STFC.pro)
    """
    alliance_id = alliance_cfg.get("id", "default")
    alliance_name = alliance_cfg.get("alliance_name")
    state = load_state(alliance_id)

    scraped_members = alliance_cfg.get("scraped_members", [])
    scrape_timestamp = alliance_cfg.get("scrape_timestamp") or datetime.utcnow().isoformat() + "Z"

    # Deserialize previous members
    prev_raw = state.get("members", {}) or {}
    prev_members = _deserialize_members(prev_raw)
    prev_by_player_id = {
        str(member.player_id): uid
        for uid, member in prev_members.items()
        if getattr(member, "player_id", None)
    }

    prev_service_state = load_json(report_state_path(alliance_id), {})
    service_state = {}

    # Build current members from scrape, matching by name where possible
    curr_members: Dict[str, Member] = {}

    for scraped in scraped_members:
        name = scraped["name"]
        scraped_player_id = scraped.get("player_id")
        prev_stats = prev_service_state.get(name, {}) or {}
        power_value = _scraped_value(scraped, "power", prev_stats.get("power", 0)) or 0
        max_power = _scraped_value(scraped, "max_power", prev_stats.get("max_power"))
        if max_power is None:
            max_power = power_value
        if max_power is not None:
            power_value = max_power
        service_state[name] = {
            "player_id": scraped_player_id,
            "helps": _scraped_value(scraped, "helps", prev_stats.get("helps", 0)) or 0,
            "rss": _scraped_value(scraped, "rss", prev_stats.get("rss", 0)) or 0,
            "iso": _scraped_value(scraped, "iso", prev_stats.get("iso", 0)) or 0,
            "power": power_value,
            "max_power": max_power or 0,
            "power_destroyed": _scraped_value(
                scraped,
                "power_destroyed",
                prev_stats.get("power_destroyed", 0),
            ) or 0,
            "arena_rating": _scraped_value(
                scraped,
                "arena_rating",
                prev_stats.get("arena_rating", 0),
            ) or 0,
            "assessment_rank": _scraped_value(
                scraped,
                "assessment_rank",
                prev_stats.get("assessment_rank", 0),
            ) or 0,
            "missions_completed": _scraped_value(
                scraped,
                "missions_completed",
                prev_stats.get("missions_completed", 0),
            ) or 0,
            "resources_mined": _scraped_value(
                scraped,
                "resources_mined",
                prev_stats.get("resources_mined", 0),
            ) or 0,
            "alliance_helps_sent": _scraped_value(
                scraped,
                "alliance_helps_sent",
                prev_stats.get("alliance_helps_sent", 0),
            ) or 0,
        }
        # Try to find an existing member by player_id first, then by name
        match_uuid = None
        fallback_reason = None
        if scraped_player_id is not None:
            match_uuid = prev_by_player_id.get(str(scraped_player_id))
            if match_uuid is None:
                fallback_reason = f"player_id {scraped_player_id} not found"
        else:
            fallback_reason = "player_id missing"
        if match_uuid is None:
            for uid, m in prev_members.items():
                if m.name == name:
                    match_uuid = uid
                    break
            if match_uuid and fallback_reason:
                log.warning(
                    "Matched %s by name (%s); player_id fallback in effect.",
                    name,
                    fallback_reason,
                )

        if match_uuid:
            # Existing member: update fields in a copy to preserve previous state
            m = _clone_member(prev_members[match_uuid])
            m.name = scraped["name"]
            m.rank = scraped.get("rank", m.rank)
            m.level = scraped.get("level", m.level)
            m.power = power_value or 0
            if scraped_player_id is not None:
                m.player_id = scraped_player_id
            join_date = scraped.get("join_date")
            combined_join = _combine_join_date(join_date, scrape_timestamp)
            if combined_join and not m.original_join_date:
                m.original_join_date = combined_join
            if combined_join and (
                not m.last_join_date
                or str(m.last_join_date).split("T", 1)[0] != join_date
            ):
                m.last_join_date = combined_join
            curr_members[match_uuid] = m
        else:
            # New member in v2: initialize from scrape
            m_json = initialize_member(scraped, scrape_timestamp)
            m = Member.from_json(m_json)
            curr_members[m.uuid] = m
            if scraped_player_id is not None:
                queue_member_detail_refresh(alliance_id, str(scraped_player_id), front=True)

    data_changed = service_state != prev_service_state

    # Run detection on Member objects
    joins, leaves, renames, promotions, demotions = detect_member_events(prev_members, curr_members)
    leaves = [member for member in leaves if not _is_repeat_leave(member)]

    # Additional event types derived here
    level_ups = _detect_level_ups(prev_members, curr_members)
    rejoins = _detect_rejoins(prev_members, curr_members)

    # Apply events to service records
    for m in joins:
        add_service_event(m, "join")

    for m in leaves:
        add_service_event(m, "leave")

    for r in renames:
        rename_event = add_service_event(
            r["member"],
            "rename",
            old_name=r["old_name"],
            new_name=r["new_name"],
        )
        append_event(
            alliance_id,
            {
                "type": "rename",
                "timestamp": rename_event["timestamp"],
                "member_uuid": r["member"].uuid,
                "member_name": r["member"].name,
                "old_name": r["old_name"],
                "new_name": r["new_name"],
                "alliance_name": alliance_name,
            },
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
        if getattr(ev["member"], "player_id", None) is not None:
            queue_member_detail_refresh(
                alliance_id,
                str(ev["member"].player_id),
                front=True,
            )

    # Prepare a flat list of events for webhook dispatch
    event_batch = []

    for m in joins:
        event_batch.append(
            {"type": "join", "member": m, "alliance_name": alliance_name}
        )
    for m in leaves:
        event_batch.append(
            {"type": "leave", "member": m, "alliance_name": alliance_name}
        )
    for r in renames:
        event_batch.append(
            {
                "type": "rename",
                "member": r["member"],
                "old_name": r["old_name"],
                "new_name": r["new_name"],
                "alliance_name": alliance_name,
            }
        )
    for p in promotions:
        event_batch.append(
            {
                "type": "promotion",
                "member": p["member"],
                "old_rank": p["old_rank"],
                "new_rank": p["new_rank"],
                "alliance_name": alliance_name,
            }
        )
    for d in demotions:
        event_batch.append(
            {
                "type": "demotion",
                "member": d["member"],
                "old_rank": d["old_rank"],
                "new_rank": d["new_rank"],
                "alliance_name": alliance_name,
            }
        )
    for ev in level_ups:
        event_batch.append(
            {
                "type": "level_up",
                "member": ev["member"],
                "old_level": ev["old_level"],
                "new_level": ev["new_level"],
                "alliance_name": alliance_name,
            }
        )
    for ev in rejoins:
        event_batch.append(
            {
                "type": "rejoin",
                "member": ev["member"],
                "last_leave": ev["last_leave"],
                "alliance_name": alliance_name,
            }
        )
    # Dispatch webhook messages for all events.
    try:
        dispatch_webhook_events(
            event_batch,
            scrape_timestamp,
            alliance_id=alliance_id,
        )
    except Exception as exc:
        # Log but do not fail the sync.
        print(f"[sync_alliance] webhook dispatch failed: {exc}")

    # Merge previous and current members so leavers stay in the history
    final_members: Dict[str, Member] = dict(prev_members)
    final_members.update(curr_members)

    state["members"] = _serialize_members(final_members)
    state["last_sync"] = scrape_timestamp
    save_state(alliance_id, state)

    report_state = report_state_path(alliance_id)
    history_snapshot = history_snapshot_path(alliance_id, scrape_timestamp)
    save_json(report_state, service_state)
    save_json(history_snapshot, service_state)
    log.info(
        "Saved service state for alliance %s (current=%s, snapshot=%s)",
        alliance_id,
        report_state,
        history_snapshot,
    )
    return data_changed

# def run_alliance_sync(alliance: dict) -> None:
#     """
#     Canonical orchestration entry point for syncing an alliance.
#     Used by cron, startup, and forcepull.
#     """
#     cfg = build_alliance_cfg(alliance)
#     run_alliance_sync(alliance)

def run_alliance_sync(alliance: dict) -> bool:
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
        "alliance_name": alliance.get("alliance_name"),
        "scraped_members": scraped_members,
        "scrape_timestamp": scrape_timestamp,
    }

    return sync_alliance(cfg)
    
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
