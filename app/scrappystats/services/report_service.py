#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 14 11:03:43 2025

@author: chris
"""

from datetime import datetime
from typing import Literal

from scrappystats.config import load_config

from .report_common import load_state_and_baseline, compute_deltas
from ..webhook.sender import post_webhook_message

ReportType = Literal["interim", "daily", "weekly"]

REPORT_TITLES = {
    "interim": "⏱️ **Interim Service Record (Today So Far)**",
    "daily":   "📊 **Daily Service Record**",
    "weekly":  "📈 **Weekly Service Record**",
}


def run_service_report(report_type: ReportType) -> None:
    """
    Unified service report runner.

    report_type:
      - interim  (today so far)
      - daily    (yesterday)
      - weekly   (last 7 days)
    """
    cfg = load_config()
    alliances = cfg.get("alliances", [])

    for alliance in alliances:
        alliance_id = alliance["id"]
        alliance_name = alliance.get("name", alliance_id)

        state, baseline = load_state_and_baseline(alliance_id, report_type)
        deltas = compute_deltas(state, baseline)

        if not deltas:
            continue

        message = format_service_report(
            alliance_name=alliance_name,
            report_type=report_type,
            deltas=deltas,
        )

        post_webhook_message(message, alliance_id=alliance_id)

def format_service_report(
    *,
    alliance_name: str,
    report_type: ReportType,
    deltas: dict,
) -> str:
    lines = [
        REPORT_TITLES[report_type],
        f"**Alliance:** {alliance_name}",
        f"**Generated:** {datetime.utcnow().isoformat()}Z",
        "",
    ]

    for category, entries in deltas.items():
        if not entries:
            continue

        lines.append(f"**{category.upper()}**")
        for entry in entries:
            lines.append(f"- {entry}")
        lines.append("")

    return "\n".join(lines)
