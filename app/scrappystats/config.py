#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 14 13:49:31 2025

@author: chris
"""

import json
import logging
import os

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.getenv("SCRAPPYSTATS_CONFIG")
FALLBACK_CONFIG_PATHS = (
    "/data/alliances.config",
    "/app/config/alliances.json",
)

<<<<<<< ours
def load_config() -> dict:
=======

def _resolve_config_path() -> str | None:
    if DEFAULT_CONFIG_PATH:
        return DEFAULT_CONFIG_PATH
    for path in FALLBACK_CONFIG_PATHS:
        if os.path.exists(path):
            return path
    return None


def load_config(*, fatal: bool = False) -> dict:
>>>>>>> theirs
    """
    Load the ScrappyStats configuration from disk.

    This is the single source of truth for config loading.
    """
    try:
        config_path = _resolve_config_path()
        if not config_path:
            raise FileNotFoundError("No config file found")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.error(
            "Config file not found. Set SCRAPPYSTATS_CONFIG or provide one of: %s",
            ", ".join(FALLBACK_CONFIG_PATHS),
        )
        if fatal:
            raise SystemExit(1)
        return {}
    except Exception:
        log.exception("Failed to load config")
        if fatal:
            raise SystemExit(1)
        return {}
