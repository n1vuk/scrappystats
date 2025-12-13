"""scrappystats.fetch_and_process

Minimal, stable entry-point used by cron + startup_init.

The refactor is in-progress; this module should *not* break imports while we
re-wire the real sync pipeline.
"""

import logging

from .legacy import fetch_alliance_page, save_raw_html
from .utils import save_json, iso_now

log = logging.getLogger(__name__)

def main():
    # Placeholder: keep runtime stable while sync is re-wired.
    log.info("fetch_and_process placeholder (refactor in progress).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
