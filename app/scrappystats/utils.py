import os
import json
from pathlib import Path
from datetime import datetime, timezone

from .version import __version__

DATA_ROOT = Path(os.environ.get("SCRAPPYSTATS_DATA_ROOT", "/data"))

STATE_DIR = DATA_ROOT / "state"
HISTORY_DIR = DATA_ROOT / "history"
ARCHIVE_DIR = DATA_ROOT / "archive"
EVENTS_DIR = DATA_ROOT / "events"
PENDING_RENAMES_DIR = DATA_ROOT / "pending_renames"

for d in (STATE_DIR, HISTORY_DIR, ARCHIVE_DIR, EVENTS_DIR, PENDING_RENAMES_DIR):
    d.mkdir(parents=True, exist_ok=True)

ALLIANCES_CONFIG = Path("/app/alliances.json")

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

def utcnow():
    return datetime.now(timezone.utc)

def iso_now():
    return utcnow().strftime(ISO_FORMAT)

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

# ---- Backward compatibility shims ----
def history_snapshot_path(*args, **kwargs):
    return snapshot_path(*args, **kwargs)

def history_meta_path(*args, **kwargs):
    return meta_path(*args, **kwargs)


# ---- Backward compatibility shims (v2.1.2) ----
def history_snapshot_path(*args, **kwargs):
    for name in (
        'snapshot_path',
        'get_snapshot_path',
        'history_snapshot',
    ):
        fn = globals().get(name)
        if callable(fn):
            return fn(*args, **kwargs)
    raise ImportError('No snapshot path helper found in utils')

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
