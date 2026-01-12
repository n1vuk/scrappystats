import logging
import os
import shutil
import subprocess
from pathlib import Path

from scrappystats.config import load_config, list_alliances
from scrappystats.services.report_service import save_report_baselines
from scrappystats.version import __version__
from scrappystats.utils import (
    ARCHIVE_DIR,
    EVENTS_DIR,
    HISTORY_DIR,
    PENDING_RENAMES_DIR,
    STATE_DIR,
)

from .log import configure_logging

configure_logging()


def _install_cron_file(*, test_mode: bool) -> None:
    source = "/app/crontab_test" if test_mode else "/app/crontab"
    dest = "/etc/cron.d/scrappystats-cron"
    try:
        shutil.copyfile(source, dest)
        os.chmod(dest, 0o644)
        logging.info("Installed %s cron file from %s", "test" if test_mode else "standard", source)
    except Exception as exc:
        logging.warning("Failed to install cron file from %s: %s", source, exc)


def _clear_alliance_test_data(alliance_id: str) -> None:
    paths = [
        Path(f"/data/alliance_{alliance_id}_state.json"),
        STATE_DIR / f"{alliance_id}.json",
        ARCHIVE_DIR / f"alliance_{alliance_id}_archive.json",
    ]
    for path in paths:
        if path.exists():
            path.unlink()

    history_dirs = [
        HISTORY_DIR / str(alliance_id),
        HISTORY_DIR / "daily",
        HISTORY_DIR / "weekly",
        HISTORY_DIR / "interim",
    ]
    for base in history_dirs:
        if base.is_dir():
            target = base / f"{alliance_id}.json"
            if target.exists():
                target.unlink()
        if base == HISTORY_DIR / str(alliance_id) and base.exists():
            shutil.rmtree(base, ignore_errors=True)

    events_dir = EVENTS_DIR / str(alliance_id)
    if events_dir.exists():
        shutil.rmtree(events_dir, ignore_errors=True)

    for path in PENDING_RENAMES_DIR.glob(f"{alliance_id}_*.json"):
        path.unlink()


def main():
    logging.info("=== ScrappyStats startup init ===")
    cfg = load_config(fatal=True)  # ← fatal if missing
    alliances = list_alliances(cfg)
    test_mode_enabled = any(
        str(alliance.get("id")) == "1" and alliance.get("test_mode")
        for alliance in alliances
    )
    _install_cron_file(test_mode=test_mode_enabled)
    if not test_mode_enabled:
        _clear_alliance_test_data("1")
    logging.info("Alliances config loaded successfully")
    logging.info("Running initial fetch_and_sync.py")
    subprocess.run(["python3", "-m", "scrappystats.fetch_and_sync"], check=False)
    # TEMP (remove in 4.0.0b): seed report baselines for existing snapshots.
    if __version__.startswith("4.0.0a"):
        logging.info("Seeding report baselines for daily/weekly reports")
        save_report_baselines("daily")
        save_report_baselines("weekly")
    logging.info("Running initial daily report")
    subprocess.run(["python3", "-m", "scrappystats.report_daily"], check=False)
    logging.info("Running initial weekly report")
    subprocess.run(["python3", "-m", "scrappystats.report_weekly"], check=False)
    logging.info("=== ScrappyStats startup init complete ===")

if __name__ == "__main__":
    main()
