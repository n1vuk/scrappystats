"""Fetch alliance data and run sync pipeline (v2)."""
import logging

from .config import load_config, list_alliances
from .log import configure_logging
from .services.fetch import fetch_alliance_roster, scrape_timestamp
from .services.test_mode import (
    format_test_mode_webhook,
    is_test_mode_enabled,
    load_test_roster,
)
from .services.sync import run_alliance_sync
from .storage.state import record_pull_history
from .utils import save_raw_json
from .webhook.sender import post_webhook_message

configure_logging()

log = logging.getLogger("scrappystats.fetch_sync")


def main() -> int:
    cfg = load_config()
    alliances = list_alliances(cfg)
    debug = bool(cfg.get("debug"))
    if not alliances:
        log.warning("No alliances configured; skipping fetch/sync.")
        return 0

    timestamp = scrape_timestamp()
    for alliance in alliances:
        alliance_id = alliance.get("id")
        if not alliance_id:
            log.warning("Alliance entry missing id; skipping: %s", alliance)
            continue
        record_source = "cron"
        try:
            if is_test_mode_enabled(alliance):
                test_payload = load_test_roster(alliance_id)
                if not test_payload:
                    record_pull_history(alliance_id, timestamp, False, source="test")
                    continue
                roster, test_timestamp, test_message, test_file = test_payload
                log.info(
                    "Test mode fetch for alliance %s using %s members at %s.",
                    alliance_id,
                    len(roster),
                    test_timestamp,
                )
                post_webhook_message(
                    format_test_mode_webhook(test_file, test_message),
                    alliance_id=alliance_id,
                )
                payload = {
                    "id": alliance_id,
                    "scraped_members": roster,
                    "scrape_timestamp": test_timestamp,
                }
                record_source = "test"
            else:
                roster = fetch_alliance_roster(alliance_id, debug=debug)
                payload = {
                    "id": alliance_id,
                    "scraped_members": roster,
                    "scrape_timestamp": timestamp,
                }
                record_source = "cron"
            if debug:
                try:
                    path = save_raw_json(alliance_id, payload, stamp=payload["scrape_timestamp"])
                    log.info("Saved raw JSON to %s", path)
                except Exception:
                    log.exception("Failed to save raw JSON for alliance %s", alliance_id)
            run_alliance_sync(payload)
            record_pull_history(alliance_id, payload["scrape_timestamp"], True, source=record_source)
        except Exception:
            log.exception("Failed to fetch/sync alliance %s", alliance_id)
            record_pull_history(alliance_id, timestamp, False, source=record_source)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
