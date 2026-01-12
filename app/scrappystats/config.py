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
    "/data/alliances.json",
    "/app/config/alliances.json",
)

def _resolve_config_path() -> str | None:
    if DEFAULT_CONFIG_PATH:
        return DEFAULT_CONFIG_PATH
    for path in FALLBACK_CONFIG_PATHS:
        if os.path.exists(path):
            return path
    return None


def load_config(*, fatal: bool = False) -> dict:
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


def member_detail_verbose(config: dict | None = None) -> bool:
    cfg = config if config is not None else load_config()
    logging_cfg = cfg.get("logging") or {}
    return bool(logging_cfg.get("member_detail_verbose", False))


def iter_alliances(config: dict):
    guilds = config.get("guilds") or []
    if guilds:
        for guild in guilds:
            for alliance in guild.get("alliances", []) or []:
                yield alliance
        return

    for alliance in config.get("alliances", []) or []:
        yield alliance


def list_alliances(config: dict) -> list:
    return list(iter_alliances(config))


def get_guild_alliances(config: dict, guild_id: str) -> list:
    guilds = config.get("guilds") or []
    if not guilds:
        return config.get("alliances", []) or []

    guild = next(
        (g for g in guilds if str(g.get("id")) == str(guild_id)),
        None,
    )
    if not guild:
        return []
    return guild.get("alliances", []) or []
