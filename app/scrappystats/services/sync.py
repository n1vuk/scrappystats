
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
<<<<<<< ours
    PENDING_RENAMES_DIR,
=======
    append_event,
>>>>>>> theirs
)
from ..models.member import Member
from .detection import detect_member_events
from .service_record import add_service_event
from .events import dispatch_webhook_events

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


def _member_join_date(member: Member) -> str:
    for attr in ("last_join_date", "original_join_date"):
        value = getattr(member, attr, None)
        if value:
            return str(value).split("T", 1)[0]
    return ""


def _within_percent(old: float, new: float, threshold: float) -> bool:
    if old == 0:
        return new == 0
    return abs(new - old) / old <= threshold


def _contrib_score(old_stats: dict, new_stats: dict) -> tuple[bool, float, list[str]]:
    try:
        old_helps = float(old_stats.get("helps", 0) or 0)
        old_rss = float(old_stats.get("rss", 0) or 0)
        old_iso = float(old_stats.get("iso", 0) or 0)
        new_helps = float(new_stats.get("helps", 0) or 0)
        new_rss = float(new_stats.get("rss", 0) or 0)
        new_iso = float(new_stats.get("iso", 0) or 0)
    except (TypeError, ValueError):
        return False, float("inf"), ["invalid contribution data"]

    helps_diff = abs(new_helps - old_helps)
    rss_match = _within_percent(old_rss, new_rss, 0.05)
    iso_match = _within_percent(old_iso, new_iso, 0.05)
    helps_match = helps_diff <= 200
    pct_rss = 0.0 if old_rss == 0 and new_rss == 0 else abs(new_rss - old_rss) / (old_rss or 1)
    pct_iso = 0.0 if old_iso == 0 and new_iso == 0 else abs(new_iso - old_iso) / (old_iso or 1)
    score = helps_diff + pct_rss + pct_iso
    notes = [
        f"helps Δ{helps_diff:.0f}",
        f"rss Δ{pct_rss:.1%}",
        f"iso Δ{pct_iso:.1%}",
    ]
    return helps_match and rss_match and iso_match, score, notes


def _clone_member(member: Member) -> Member:
    return Member.from_json(member.to_json())


def _reconcile_name_changes(
    prev_members: Dict[str, Member],
    curr_members: Dict[str, Member],
    prev_service_state: dict,
    curr_service_state: dict,
    scrape_timestamp: str,
    alliance_id: str,
) -> list[dict]:
    join_ids = [uid for uid in curr_members if uid not in prev_members]
    leave_ids = [uid for uid in prev_members if uid not in curr_members]
    if not join_ids or not leave_ids:
        return []

    pending_events: list[dict] = []
    pending_records: list[dict] = []
    unmatched_leaves = set(leave_ids)

    for join_id in join_ids:
        if not unmatched_leaves:
            break
        join_member = curr_members[join_id]
        join_date = _member_join_date(join_member)

        guaranteed = [
            leave_id
            for leave_id in sorted(unmatched_leaves, key=lambda uid: prev_members[uid].name.lower())
            if (
                prev_members[leave_id].level == join_member.level
                and _member_join_date(prev_members[leave_id]) == join_date
                and join_date
            )
        ]

        matched_leave = None
        if len(guaranteed) == 1:
            matched_leave = guaranteed[0]
        elif len(guaranteed) > 1:
            matched_leave = guaranteed[0]
        else:
            best_score = float("inf")
            best_leave = None
            best_notes: list[str] = []
            for leave_id in unmatched_leaves:
                old_member = prev_members[leave_id]
                old_stats = prev_service_state.get(old_member.name, {})
                new_stats = curr_service_state.get(join_member.name, {})
                if not old_stats or not new_stats:
                    continue
                matched, score, notes = _contrib_score(old_stats, new_stats)
                if matched and score < best_score:
                    best_score = score
                    best_leave = leave_id
                    best_notes = notes
            if best_leave:
                matched_leave = best_leave
            else:
                # Flag for manual review if we have any leaves to compare against.
                candidate_leave = sorted(
                    unmatched_leaves,
                    key=lambda uid: prev_members[uid].name.lower(),
                )[0]
                old_member = prev_members[candidate_leave]
                old_stats = prev_service_state.get(old_member.name, {})
                new_stats = curr_service_state.get(join_member.name, {})
                matched, score, notes = _contrib_score(old_stats, new_stats) if old_stats and new_stats else (
                    False,
                    float("inf"),
                    ["no contribution data"],
                )
                pending_events.append(
                    {
                        "type": "rename_review",
                        "old_name": old_member.name,
                        "new_name": join_member.name,
                        "reason": "Manual review required",
                        "notes": ", ".join(notes),
                        "scrape_timestamp": scrape_timestamp,
                        "alliance_id": alliance_id,
                    }
                )
                pending_records.append(
                    {
                        "old_name": old_member.name,
                        "new_name": join_member.name,
                        "reason": "manual_review",
                        "notes": notes,
                        "matched": matched,
                        "score": score,
                        "timestamp": scrape_timestamp,
                    }
                )
                continue

        if matched_leave:
            old_member = prev_members[matched_leave]
            updated = _clone_member(old_member)
            updated.name = join_member.name
            updated.rank = join_member.rank
            updated.level = join_member.level
            if old_member.name not in updated.previous_names:
                updated.previous_names.append(old_member.name)
            curr_members[matched_leave] = updated
            del curr_members[join_id]
            unmatched_leaves.discard(matched_leave)

    if pending_records:
        safe_stamp = scrape_timestamp.replace(":", "-")
        pending_path = PENDING_RENAMES_DIR / f"{alliance_id}_{safe_stamp}.json"
        save_json(pending_path, pending_records)

    return pending_events


def sync_alliance(alliance_cfg: dict) -> None:
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

    prev_service_state = load_json(report_state_path(alliance_id), {})
    service_state = {}

    # Build current members from scrape, matching by name where possible
    curr_members: Dict[str, Member] = {}

    for scraped in scraped_members:
        name = scraped["name"]
        service_state[name] = {
            "helps": scraped.get("helps", 0) or 0,
            "rss": scraped.get("rss", 0) or 0,
            "iso": scraped.get("iso", 0) or 0,
        }
        # Try to find an existing member with this name
        match_uuid = None
        for uid, m in prev_members.items():
            if m.name == name:
                match_uuid = uid
                break

        if match_uuid:
            # Existing member: update fields in a copy to preserve previous state
            m = _clone_member(prev_members[match_uuid])
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

    pending_rename_events = _reconcile_name_changes(
        prev_members,
        curr_members,
        prev_service_state,
        service_state,
        scrape_timestamp,
        alliance_id,
    )

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
    for ev in pending_rename_events:
        ev["alliance_name"] = alliance_name
        event_batch.append(ev)

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
        "alliance_name": alliance.get("alliance_name"),
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
