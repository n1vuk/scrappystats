# scrappystats/legacy.py
"""
Compatibility layer for pre-refactor imports.

This module MUST NOT:
- define paths
- create directories
- implement logic

It only re-exports canonical helpers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

# ---- Canonical implementation ----
from scrappystats.services.fetch_legacy import fetch_alliance_page

# ---- Canonical storage helpers ----
from scrappystats.utils import (
    state_path,
    events_path,
    archive_path,
    history_snapshot_path,
    history_meta_path,
    save_raw_html,
)

# ---- Directory aliases (derived ONLY) ----
STATE_DIR   = Path(state_path("_probe")).parent
EVENTS_DIR  = Path(events_path("_probe")).parent
ARCHIVE_DIR = Path(archive_path("_probe")).parent
HISTORY_DIR = Path(history_snapshot_path("_probe")).parent

# ---- Legacy helper ----
def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
