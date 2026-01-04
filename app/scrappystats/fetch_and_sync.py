"""Fetch alliance data and run sync pipeline (v2)."""
import logging

from .config import load_config
from .log import configure_logging
from .services.fetch import fetch_alliance_roster, scrape_timestamp
from .services.sync import run_alliance_sync
from .utils import save_raw_json

configure_logging()

log = logging.getLogger("scrappystats.fetch_sync")


def main() -> int:
    cfg = load_config()
    alliances = cfg.get("alliances", [])
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
        try:
            roster = fetch_alliance_roster(alliance_id, debug=debug)
            payload = {
                "id": alliance_id,
                "scraped_members": roster,
                "scrape_timestamp": timestamp,
            }
            if debug:
                try:
                    path = save_raw_json(alliance_id, payload, stamp=timestamp)
                    log.info("Saved raw JSON to %s", path)
                except Exception:
                    log.exception("Failed to save raw JSON for alliance %s", alliance_id)
            run_alliance_sync(payload)
        except Exception:
            log.exception("Failed to fetch/sync alliance %s", alliance_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
