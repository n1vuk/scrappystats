"""scrappystats.legacy

Compatibility layer to keep older entry-points working while the refactor
settles. **Do not** import internal path/layout details from random modules.
If an older module needs something, add it here and keep the rest of the
codebase clean.

This project is deployed from ZIPs (no manual edits), so this file must be
self-contained and conservative.
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Data root inside the container. Keep in sync with utils.DATA_ROOT default.
DATA_ROOT = Path(os.environ.get("SCRAPPYSTATS_DATA_ROOT", "/data"))

STATE_DIR = DATA_ROOT / "state"
HISTORY_DIR = DATA_ROOT / "history"
EVENTS_DIR = DATA_ROOT / "events"
ARCHIVE_DIR = DATA_ROOT / "archive"
RAW_HTML_DIR = ARCHIVE_DIR / "raw_html"

for d in (STATE_DIR, HISTORY_DIR, EVENTS_DIR, ARCHIVE_DIR, RAW_HTML_DIR):
    d.mkdir(parents=True, exist_ok=True)

def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

# ---- Legacy sync API (stubs until refactor is finished) ----
def fetch_alliance_page(*args, **kwargs):
    """Legacy name used by older fetch_and_process implementations.

    The refactor moved this logic; until it is re-wired, keep the name
    available so imports don't crash. If you hit this at runtime, wire it
    to the real sync implementation.
    """
    raise NotImplementedError(
        "fetch_alliance_page is not wired yet in this refactor build. "
        "Import is provided for compatibility; connect it to services.sync."
    )

# ---- Legacy path helpers ----
def state_path(alliance_id: str) -> str:
    return str(STATE_DIR / f"alliance_{alliance_id}_state.json")

def events_path(alliance_id: str) -> str:
    return str(EVENTS_DIR / f"alliance_{alliance_id}_events.json")

def history_snapshot_path(alliance_id: str, stamp: Optional[str] = None) -> str:
    stamp = stamp or _utc_ts()
    return str(HISTORY_DIR / f"alliance_{alliance_id}_snapshot_{stamp}.json")

def history_meta_path(alliance_id: str, stamp: Optional[str] = None) -> str:
    stamp = stamp or _utc_ts()
    return str(HISTORY_DIR / f"alliance_{alliance_id}_meta_{stamp}.json")

# ---- Legacy storage helpers ----
def save_raw_html(alliance_id: str, html: str, stamp: Optional[str] = None) -> str:
    """Persist raw HTML for debugging / audit."""
    stamp = stamp or _utc_ts()
    path = RAW_HTML_DIR / f"alliance_{alliance_id}_{stamp}.html"
    path.write_text(html or "", encoding="utf-8")
    return str(path)
