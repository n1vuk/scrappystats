import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from .config import load_config, list_alliances

DATA_ROOT = Path(os.environ.get("SCRAPPYSTATS_DATA_ROOT", "/data"))

STATE_DIR = DATA_ROOT / "state"
SNAPSHOT_DIR = DATA_ROOT / "snapshots"
HISTORY_DIR = DATA_ROOT / "history"
ARCHIVE_DIR = DATA_ROOT / "archive"
EVENTS_DIR = DATA_ROOT / "events"
PENDING_RENAMES_DIR = DATA_ROOT / "pending_renames"
EVENT_RETENTION_DAYS = int(os.environ.get("SCRAPPYSTATS_EVENT_RETENTION_DAYS", "0") or 0)
def archive_path(alliance_id: str) -> str:
    """
    Path to archived players for an alliance.
    """
    return str(ARCHIVE_DIR / f"alliance_{alliance_id}_archive.json")

def events_path(alliance_id: str, date_str: str | None = None) -> str:
    date_str = date_str or utcnow().date().isoformat()
    alliance_dir = EVENTS_DIR / str(alliance_id)
    alliance_dir.mkdir(parents=True, exist_ok=True)
    return str(alliance_dir / f"{date_str}.json")

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

for d in (STATE_DIR, HISTORY_DIR, ARCHIVE_DIR, EVENTS_DIR, PENDING_RENAMES_DIR):
    d.mkdir(parents=True, exist_ok=True)

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    
def state_path(alliance_id: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{alliance_id}.json"

def history_snapshot_path(alliance_id: str, ts: str) -> Path:
    """
    Return path to a historical snapshot for an alliance at timestamp ts.
    ts is expected to be an ISO-like string (e.g. 2025-12-15T00:00)
    """
    return HISTORY_DIR / alliance_id / f"{ts}.json"


def iso_now():
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


def parse_iso(ts: str) -> datetime:
    return datetime.strptime(ts, ISO_FORMAT).replace(tzinfo=timezone.utc)

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def load_alliances():
    config = load_config()
    return {
        **config,
        "alliances": list_alliances(config),
    }

def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(path)


def history_meta_path(*args, **kwargs):
    for name in (
        'meta_path',
        'get_meta_path',
        'history_meta',
    ):
        fn = globals().get(name)
        if callable(fn):
            return fn(*args, **kwargs)
    raise ImportError('No meta path helper found in utils')
    

def append_event(alliance_id: str, event: dict) -> None:
    """
    Append a single event to the alliance events file.
    """
    date_str = _event_date(event)
    path = events_path(alliance_id, date_str)
    events = load_json(path, [])
    events.append(event)
    save_json(path, events)
    _prune_event_history(alliance_id)


def _event_date(event: dict) -> str:
    for key in ("timestamp", "stardate", "scrape_timestamp"):
        raw = event.get(key)
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return parsed.date().isoformat()
        except ValueError:
            continue
    return utcnow().date().isoformat()


def _prune_event_history(alliance_id: str) -> None:
    if EVENT_RETENTION_DAYS <= 0:
        return
    cutoff = utcnow().date() - timedelta(days=EVENT_RETENTION_DAYS)
    alliance_dir = EVENTS_DIR / str(alliance_id)
    if not alliance_dir.exists():
        return
    for file in alliance_dir.glob("*.json"):
        try:
            file_date = datetime.fromisoformat(file.stem).date()
        except ValueError:
            continue
        if file_date < cutoff:
            file.unlink()

def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def save_raw_html(alliance_id: str, html: str, stamp: str | None = None) -> str:
    """
    Persist raw alliance HTML for debugging / audit.
    """
    stamp = stamp or _utc_ts()
    path = Path(ARCHIVE_DIR) / "raw_html"
    path.mkdir(parents=True, exist_ok=True)

    file = path / f"alliance_{alliance_id}_{stamp}.html"
    file.write_text(html or "", encoding="utf-8")
    return str(file)


def save_raw_json(alliance_id: str, data: dict, stamp: str | None = None) -> str:
    """
    Persist raw alliance JSON for debugging / audit.
    """
    stamp = stamp or _utc_ts()
    path = Path(ARCHIVE_DIR) / "raw_json"
    path.mkdir(parents=True, exist_ok=True)

    file = path / f"alliance_{alliance_id}_{stamp}.json"
    file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return str(file)
