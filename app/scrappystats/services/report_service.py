#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 14 11:03:43 2025

@author: chris
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from scrappystats.config import load_config, list_alliances, get_guild_alliances
from scrappystats.utils import HISTORY_DIR, save_json

from .report_common import (
    load_state_and_baseline,
    compute_deltas,
    make_table,
    load_snapshot_at_or_before,
)
from ..webhook.sender import post_webhook_message

log = logging.getLogger(__name__)

ReportType = Literal["interim", "daily", "weekly"]

REPORT_TITLES = {
    "interim": "⏱️ **Interim Service Record (Today So Far)**",
    "daily":   "📊 **Daily Service Record**",
    "weekly":  "📈 **Weekly Service Record**",
}


def build_service_reports(
    report_type: ReportType,
    *,
    guild_id: str | None = None,
) -> list[tuple[str, str]]:
    """
    Build report messages for each alliance.
    """
    cfg = load_config()
    if guild_id:
        alliances = get_guild_alliances(cfg, guild_id)
    else:
        alliances = list_alliances(cfg)

    reports: list[tuple[str, str]] = []

    now = datetime.now(timezone.utc)
    start_of_today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    if report_type == "interim":
        start_dt = start_of_today
        end_dt = now
    elif report_type == "daily":
        start_dt = start_of_today - timedelta(days=1)
        end_dt = start_of_today
    else:
        start_dt = start_of_today - timedelta(days=7)
        end_dt = start_of_today

    for alliance in alliances:
        alliance_id = alliance["id"]
        alliance_name = alliance.get("name", alliance_id)

        state, baseline = load_state_and_baseline(alliance_id, report_type)
        start_snapshot = load_snapshot_at_or_before(alliance_id, start_dt)
        end_snapshot = load_snapshot_at_or_before(alliance_id, end_dt)
        current = end_snapshot or state
        
        if report_type == "interim":
            previous = start_snapshot or current
        else:
            previous = start_snapshot or baseline
        if report_type == "interim" and start_snapshot is None:
            previous = current 
        deltas = compute_deltas(current, previous)

        message = format_service_report(
            alliance_name=alliance_name,
            report_type=report_type,
            deltas=deltas,
        )
        if not message:
            continue

        reports.append((alliance_id, message))

    return reports


def run_service_report(report_type: ReportType) -> None:
    """
    Unified service report runner.

    report_type:
      - interim  (today so far)
      - daily    (yesterday)
      - weekly   (last 7 days)
    """
    reports = build_service_reports(report_type)
    for alliance_id, message in reports:
        post_webhook_message(message, alliance_id=alliance_id)
    save_report_baselines(report_type)


def save_report_baselines(report_type: ReportType, *, guild_id: str | None = None) -> None:
    """
    Persist the current service state as the baseline for future reports.
    """
    cfg = load_config()
    if guild_id:
        alliances = get_guild_alliances(cfg, guild_id)
    else:
        alliances = list_alliances(cfg)

    for alliance in alliances:
        alliance_id = alliance["id"]
        state, _ = load_state_and_baseline(alliance_id, report_type)
        baseline_path = HISTORY_DIR / report_type / f"{alliance_id}.json"
        save_json(baseline_path, state)
        log.info(
            "Saved %s baseline for alliance %s at %s",
            report_type,
            alliance_id,
            baseline_path,
        )

def format_service_report(
    *,
    alliance_name: str,
    report_type: ReportType,
    deltas: dict,
) -> str | None:
    rows = []
    for member_name in sorted(deltas.keys()):
        delta = deltas[member_name]
        helps = delta.get("helps", 0)
        rss = delta.get("rss", 0)
        iso = delta.get("iso", 0)
        if helps == 0 and rss == 0 and iso == 0:
            continue
        rows.append([member_name, helps, rss, iso])

    if not rows:
        return None

    table = make_table(["Member", "Helps", "RSS", "ISO"], rows)

    lines = [
        REPORT_TITLES[report_type],
        f"**Alliance:** {alliance_name}",
        f"**Generated:** {datetime.utcnow().isoformat()}Z",
        "",
        "```",
        table,
        "```",
    ]

    return "\n".join(lines)
