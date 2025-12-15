import os
import json
from pathlib import Path
from datetime import datetime, timezone


DATA_ROOT = Path(os.environ.g1et("SCRAPPYSTATS_DATA_ROOT", "/data"))

STATE_DIR = Path("/app/data/state")
SNAPSHOT_DIR = Path("/app/data/snapshots")
HISTORY_DIR = DATA_ROOT / "history"
ARCHIVE_DIR = DATA_ROOT / "archive"
EVENTS_DIR = DATA_ROOT / "events"
PENDING_RENAMES_DIR = DATA_ROOT / "pending_renames"

for d in (STATE_DIR, HISTORY_DIR, ARCHIVE_DIR, EVENTS_DIR, PENDING_RENAMES_DIR):
    d.mkdir(parents=True, exist_ok=True)

ALLIANCES_CONFIG = Path("/app/alliances.json")

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
    return load_json(ALLIANCES_CONFIG, {})

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
    

