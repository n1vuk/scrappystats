#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 14 13:49:31 2025

@author: chris
"""

import json
import os
import logging

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = os.getenv(
    "SCRAPPYSTATS_CONFIG",
    "/data/alliances.config",
)

def load_config() -> dict:
    """
    Load the ScrappyStats configuration from disk.

    This is the single source of truth for config loading.
    """
    try:
        with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.error("Config file not found: %s", DEFAULT_CONFIG_PATH)
        return {}
    except Exception:
        log.exception("Failed to load config")
        return {}
