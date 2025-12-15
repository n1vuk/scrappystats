#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec 15 17:30:43 2025

@author: chris
"""

# scrappystats/services/fetch_legacy.py

import logging
import requests
from bs4 import BeautifulSoup

from scrappystats.utils import (
    load_alliances,
    state_path,
    archive_path,
    append_event,
    iso_now,
    save_json,
    load_json,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BASE_URL = "https://stfc.pro/alliance/"

def fetch_alliance_page(alliance_id: str) -> str:
    url = BASE_URL + alliance_id
    logging.info("Fetching %s", url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text

def parse_number(txt: str) -> int:
    txt = txt.replace(",", "").strip()
    if not txt:
        return 0
    if txt.endswith("K"):
        try:
            return int(float(txt[:-1]) * 1000)
        except Exception:
            return 0
    if txt.endswith("M"):
        try:
            return int(float(txt[:-1]) * 1_000_000)
        except Exception:
            return 0
    try:
        return int(txt)
    except ValueError:
        try:
            return int(float(txt))
        except Exception:
            return 0

def parse_roster(html: str):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        raise RuntimeError("Roster table not found")

    roster = {}
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 7:
            continue

        name_span = tds[1].find("span", class_="cursor-pointer")
        if not name_span:
            continue
        name = name_span.get_text(strip=True)
        if not name:
            continue

        role_div = tds[2].find("div", class_="ml-0")
        role = role_div.get_text(strip=True) if role_div else "Agent"

        try:
            level = int(tds[3].get_text(strip=True))
        except Exception:
            level = 0

        rss = parse_number(tds[4].get_text(strip=True))
        iso = parse_number(tds[5].get_text(strip=True))
        join_date = tds[6].get_text(strip=True)

        roster[name] = {
            "name": name,
            "role": role,
            "level": level,
            "rss": rss,
            "iso": iso,
            "join_date_recent": join_date,
        }

    return roster

def ensure_membership_fields(player: dict):
    join_recent = player.get("join_date_recent") or ""
    original = player.get("join_date_original") or join_recent
    join_dates = player.get("join_dates") or ([] if not join_recent else [join_recent])
    left_dates = player.get("left_dates") or []

    player.setdefault("join_date_original", original)
    player.setdefault("join_date_recent", join_recent)
    player.setdefault("join_dates", join_dates)
    player.setdefault("left_dates", left_dates)
    return player

def process_alliance(alliance: dict, admin_webhook: str | None):
    alliance_id = alliance["id"]
    name = alliance.get("name", alliance_id)

    html = fetch_alliance_page(alliance_id)
    roster = parse_roster(html)

    state_file = state_path(alliance_id)
    archive_file = archive_path(alliance_id)

    prev_state = load_json(state_file, {})
    archive = load_json(archive_file, {})

    now_iso = iso_now()

    current_names = set(roster.keys())
    previous_names = set(prev_state.keys())

    joined = current_names - previous_names
    left = previous_names - current_names

    for player_name in joined:
        pdata = ensure_membership_fields(roster[player_name])
        if player_name in archive:
            old = archive[player_name]
            pdata["join_date_original"] = old.get("join_date_original") or pdata["join_date_recent"]
            join_dates = old.get("join_dates", [])
            if pdata.get("join_date_recent") and pdata["join_date_recent"] not in join_dates:
                join_dates.append(pdata["join_date_recent"])
            pdata["join_dates"] = join_dates
            pdata["left_dates"] = old.get("left_dates", [])
            event_type = "rejoin"
        else:
            event_type = "join"

        pdata["last_seen"] = now_iso
        prev_state[player_name] = pdata

        append_event(alliance_id, {
            "timestamp": now_iso,
            "type": event_type,
            "player": player_name,
            "alliance": alliance_id,
        })

        logging.info("[%s] %s: %s", name, event_type.capitalize(), player_name)

    for player_name in left:
        pdata = ensure_membership_fields(prev_state[player_name])
        pdata.setdefault("left_dates", []).append(now_iso[:10])
        archive[player_name] = pdata

        append_event(alliance_id, {
            "timestamp": now_iso,
            "type": "leave",
            "player": player_name,
            "alliance": alliance_id,
        })

        logging.info("[%s] Leave: %s", name, player_name)
        del prev_state[player_name]

    for player_name in current_names & previous_names:
        old = prev_state[player_name]
        cur = ensure_membership_fields(roster[player_name])

        cur["join_date_original"] = old.get("join_date_original")
        cur["join_dates"] = old.get("join_dates", [])
        cur["left_dates"] = old.get("left_dates", [])
        cur["last_seen"] = now_iso

        if cur.get("level", 0) > old.get("level", 0):
            append_event(alliance_id, {
                "timestamp": now_iso,
                "type": "level_up",
                "player": player_name,
                "from_level": old.get("level"),
                "to_level": cur.get("level"),
                "alliance": alliance_id,
            })

        if cur.get("role") != old.get("role"):
            append_event(alliance_id, {
                "timestamp": now_iso,
                "type": "promotion",
                "player": player_name,
                "from_rank": old.get("role"),
                "to_rank": cur.get("role"),
                "alliance": alliance_id,
            })

        prev_state[player_name] = cur

    save_json(state_file, prev_state)
    save_json(archive_file, archive)

def main():
    logging.info("=== ScrappyStats fetch_and_process start ===")
    cfg = load_alliances()
    admin_webhook = cfg.get("admin_webhook")

    for alliance in cfg.get("alliances", []):
        try:
            process_alliance(alliance, admin_webhook)
        except Exception as e:
            logging.exception("Error processing alliance %s: %s", alliance.get("id"), e)

    logging.info("=== ScrappyStats fetch_and_process complete ===")

def run_all() -> str:
    try:
        main()
        return "OK"
    except Exception as e:
        logging.exception("Error during run_all: %s", e)
        return f"error: {e}"
