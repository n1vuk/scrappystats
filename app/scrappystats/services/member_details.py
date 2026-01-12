import logging
import os
from datetime import datetime, timedelta, timezone

from ..config import load_config, list_alliances
from ..models.member import Member
from ..storage.state import load_state, save_state
from ..utils import iso_now, load_json, save_json, state_path as report_state_path
from .fetch import fetch_member_details_api

log = logging.getLogger("scrappystats.member_details")

DETAIL_INTERVAL_HOURS = float(os.getenv("SCRAPPYSTATS_MEMBER_DETAIL_INTERVAL_HOURS", "60") or 60)
DETAILS_PER_RUN = int(os.getenv("SCRAPPYSTATS_MEMBER_DETAIL_PER_RUN", "1") or 1)
FAILURE_BACKOFF_MINUTES = float(os.getenv("SCRAPPYSTATS_MEMBER_DETAIL_FAILURE_BACKOFF_MINUTES", "30") or 30)

QUEUE_KEY = "member_detail_queue"
DETAIL_STATE_KEY = "member_detail"
OVERRIDE_KEY = "member_detail_overrides"


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _eligible_by_interval(last_success: str | None, *, interval_hours: float) -> bool:
    if not last_success:
        return True
    parsed = _parse_iso(last_success)
    if not parsed:
        return True
    return _now() - parsed >= timedelta(hours=interval_hours)


def _eligible_by_backoff(last_attempt: str | None) -> bool:
    if not last_attempt:
        return True
    parsed = _parse_iso(last_attempt)
    if not parsed:
        return True
    return _now() - parsed >= timedelta(minutes=FAILURE_BACKOFF_MINUTES)


def queue_member_detail_refresh(alliance_id: str, player_id: str, *, front: bool = False) -> None:
    state = load_state(alliance_id)
    queue = list(state.get(QUEUE_KEY) or [])
    pid = str(player_id)
    if pid in queue:
        if front:
            queue = [pid] + [item for item in queue if item != pid]
    else:
        if front:
            queue.insert(0, pid)
        else:
            queue.append(pid)
    state[QUEUE_KEY] = queue
    save_state(alliance_id, state)


def set_member_detail_interval_override(
    alliance_id: str,
    player_id: str,
    interval_hours: float | None,
) -> None:
    state = load_state(alliance_id)
    overrides = dict(state.get(OVERRIDE_KEY) or {})
    pid = str(player_id)
    if interval_hours is None:
        overrides.pop(pid, None)
    else:
        overrides[pid] = {"interval_hours": float(interval_hours)}
    state[OVERRIDE_KEY] = overrides
    save_state(alliance_id, state)


def _member_index(state: dict) -> tuple[dict[str, Member], dict[str, Member]]:
    members_raw = state.get("members", {}) or {}
    by_name: dict[str, Member] = {}
    by_player_id: dict[str, Member] = {}
    for data in members_raw.values():
        member = Member.from_json(data)
        if member.name:
            by_name[member.name] = member
        if member.player_id:
            by_player_id[str(member.player_id)] = member
    return by_name, by_player_id


def _load_service_state(alliance_id: str) -> dict:
    return load_json(report_state_path(alliance_id), {})


def _save_service_state(alliance_id: str, service_state: dict) -> None:
    save_json(report_state_path(alliance_id), service_state)


def _select_candidate(
    alliance_id: str,
    *,
    max_members: int,
) -> list[tuple[str, Member]]:
    state = load_state(alliance_id)
    detail_state = state.get(DETAIL_STATE_KEY) or {}
    overrides = state.get(OVERRIDE_KEY) or {}
    queue = list(state.get(QUEUE_KEY) or [])
    by_name, by_player_id = _member_index(state)

    service_state = _load_service_state(alliance_id)
    active_names = set(service_state.keys())

    def _eligible_for_player(pid: str) -> bool:
        entry = detail_state.get(pid) or {}
        if not _eligible_by_backoff(entry.get("last_attempt")):
            return False
        interval = overrides.get(pid, {}).get("interval_hours", DETAIL_INTERVAL_HOURS)
        return _eligible_by_interval(entry.get("last_success"), interval_hours=interval)

    candidates: list[tuple[str, Member]] = []
    if queue:
        remaining: list[str] = []
        for pid in queue:
            if len(candidates) >= max_members:
                remaining.append(str(pid))
                continue
            member = by_player_id.get(str(pid))
            if not member:
                continue
            if not _eligible_for_player(str(pid)):
                remaining.append(str(pid))
                continue
            candidates.append((str(pid), member))
        state[QUEUE_KEY] = remaining
        save_state(alliance_id, state)
        if candidates:
            return candidates

    eligible: list[tuple[datetime, str, Member]] = []
    for name in active_names:
        member = by_name.get(name)
        if not member or not member.player_id:
            continue
        pid = str(member.player_id)
        entry = detail_state.get(pid) or {}
        if not _eligible_by_backoff(entry.get("last_attempt")):
            continue
        interval = overrides.get(pid, {}).get("interval_hours", DETAIL_INTERVAL_HOURS)
        if not _eligible_by_interval(entry.get("last_success"), interval_hours=interval):
            continue
        last_success = _parse_iso(entry.get("last_success")) or datetime.min.replace(tzinfo=timezone.utc)
        eligible.append((last_success, pid, member))

    eligible.sort(key=lambda item: item[0])
    for _, pid, member in eligible[:max_members]:
        candidates.append((pid, member))
    return candidates


def _update_member_detail(
    alliance_id: str,
    player_id: str,
    member: Member,
) -> bool:
    state = load_state(alliance_id)
    detail_state = state.get(DETAIL_STATE_KEY) or {}
    entry = detail_state.get(str(player_id)) or {}
    entry["last_attempt"] = iso_now()
    detail_state[str(player_id)] = entry
    state[DETAIL_STATE_KEY] = detail_state
    save_state(alliance_id, state)

    service_state = _load_service_state(alliance_id)
    if member.name not in service_state:
        log.info("Skipping member detail update for %s: not in active roster.", member.name)
        return False

    try:
        detail_stats, _payload = fetch_member_details_api(str(player_id))
    except Exception as exc:
        log.warning("Member detail fetch failed for %s: %s", player_id, exc)
        entry["last_error"] = str(exc)
        detail_state[str(player_id)] = entry
        state[DETAIL_STATE_KEY] = detail_state
        save_state(alliance_id, state)
        return False

    if not detail_stats:
        log.info("No detail stats returned for %s.", player_id)
        return False

    member_state = service_state.get(member.name, {}) or {}
    member_state.update(detail_stats)
    if detail_stats.get("max_power") is not None:
        member_state["power"] = detail_stats["max_power"]
    service_state[member.name] = member_state
    _save_service_state(alliance_id, service_state)

    entry["last_success"] = iso_now()
    entry.pop("last_error", None)
    detail_state[str(player_id)] = entry
    state[DETAIL_STATE_KEY] = detail_state
    save_state(alliance_id, state)
    return True


def run_member_detail_worker(*, alliance_id: str | None = None, max_members: int | None = None) -> int:
    config = load_config()
    alliances = list_alliances(config)
    if alliance_id:
        alliances = [a for a in alliances if str(a.get("id")) == str(alliance_id)]
    if not alliances:
        log.info("No alliances configured for member detail worker.")
        return 0

    updated = 0
    limit = max_members if max_members is not None else DETAILS_PER_RUN
    for alliance in alliances:
        if updated >= limit:
            break
        aid = alliance.get("id")
        if not aid:
            continue
        candidates = _select_candidate(aid, max_members=limit - updated)
        for player_id, member in candidates:
            if _update_member_detail(aid, player_id, member):
                updated += 1
            if updated >= limit:
                break

    return updated
