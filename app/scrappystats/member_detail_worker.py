import argparse
import logging

from scrappystats.log import configure_logging
from scrappystats.services.member_details import (
    queue_member_detail_refresh,
    run_member_detail_worker,
    set_member_detail_interval_override,
)

configure_logging()
log = logging.getLogger("scrappystats.member_detail_worker")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ScrappyStats member detail background worker.",
    )
    parser.add_argument(
        "--alliance-id",
        help="Limit the worker to a single alliance id.",
    )
    parser.add_argument(
        "--max-members",
        type=int,
        help="Maximum members to process in this run.",
    )
    parser.add_argument(
        "--force",
        nargs=2,
        metavar=("ALLIANCE_ID", "PLAYER_ID"),
        help="Queue a member detail refresh immediately.",
    )
    parser.add_argument(
        "--override-interval",
        nargs=3,
        metavar=("ALLIANCE_ID", "PLAYER_ID", "HOURS"),
        help="Override member detail interval hours (<=0 clears).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.force:
        alliance_id, player_id = args.force
        queue_member_detail_refresh(alliance_id, player_id)
        log.info("Queued member detail refresh for %s (%s).", player_id, alliance_id)
        return 0

    if args.override_interval:
        alliance_id, player_id, hours = args.override_interval
        try:
            interval = float(hours)
        except ValueError:
            log.error("Invalid interval hours: %s", hours)
            return 2
        if interval <= 0:
            set_member_detail_interval_override(alliance_id, player_id, None)
            log.info("Cleared member detail interval override for %s (%s).", player_id, alliance_id)
        else:
            set_member_detail_interval_override(alliance_id, player_id, interval)
            log.info(
                "Set member detail interval override for %s (%s) to %.2f hours.",
                player_id,
                alliance_id,
                interval,
            )
        return 0

    processed = run_member_detail_worker(
        alliance_id=args.alliance_id,
        max_members=args.max_members,
    )
    log.info("Member detail worker processed %s member(s).", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
