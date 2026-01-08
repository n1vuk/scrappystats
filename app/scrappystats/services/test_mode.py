import logging
import os
from pathlib import Path

from .fetch import scrape_timestamp
from ..utils import load_json, save_json

log = logging.getLogger(__name__)

TEST_DATA_DIR = Path(os.environ.get("SCRAPPYSTATS_TEST_DATA_DIR", "/data/test"))
TEST_CURSOR_PATH = TEST_DATA_DIR / ".cursor.json"


def is_test_mode_enabled(alliance: dict) -> bool:
    enabled = str(alliance.get("id")) == "1" and bool(alliance.get("test_mode"))
    if enabled:
        log.info("Test mode enabled for alliance 1.")
    return enabled


def load_test_roster(alliance_id: str) -> tuple[list[dict], str] | None:
    if str(alliance_id) != "1":
        return None

    if not TEST_DATA_DIR.exists():
        log.warning("Test mode enabled but %s does not exist.", TEST_DATA_DIR)
        return None

    files = _sorted_test_files()
    if not files:
        log.warning("Test mode enabled but no JSON files found in %s.", TEST_DATA_DIR)
        return None

    cursor = load_json(TEST_CURSOR_PATH, {})
    last_name = cursor.get("last_file")
    next_file = _next_file(files, last_name)
    log.info(
        "Test mode loading roster from %s (last_file=%s).",
        next_file.name,
        last_name or "none",
    )
    data = load_json(next_file, None)
    if data is None:
        log.warning("Failed to load test data file %s.", next_file)
        return None

    cursor["last_file"] = next_file.name
    save_json(TEST_CURSOR_PATH, cursor)
    log.info("Test mode advanced cursor to %s.", next_file.name)

    try:
        roster, ts = _extract_roster_and_timestamp(data)
    except ValueError as exc:
        log.warning("Invalid test data file %s: %s", next_file, exc)
        return None
    return roster, ts


def _sorted_test_files() -> list[Path]:
    files = [path for path in TEST_DATA_DIR.iterdir() if path.suffix == ".json"]
    return sorted(files, key=_sort_key)


def _sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem
    digits = "".join(char for char in stem if char.isdigit())
    if digits:
        return int(digits), stem
    return (1_000_000_000, stem)


def _next_file(files: list[Path], last_name: str | None) -> Path:
    if not last_name:
        return files[0]
    for idx, path in enumerate(files):
        if path.name == last_name:
            return files[idx + 1] if idx + 1 < len(files) else files[-1]
    return files[0]


def _extract_roster_and_timestamp(data: object) -> tuple[list[dict], str]:
    timestamp = scrape_timestamp()
    if isinstance(data, dict):
        timestamp = data.get("scrape_timestamp") or timestamp
        for key in ("scraped_members", "members", "roster"):
            roster = data.get(key)
            if isinstance(roster, list):
                return roster, timestamp
        if isinstance(data.get("data"), list):
            return data["data"], timestamp
    if isinstance(data, list):
        return data, timestamp
    raise ValueError("Test data must be a list or dict with roster data.")
