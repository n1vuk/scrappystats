"""Fetch alliance roster data from STFC.pro (v2 pipeline)."""
import logging
from datetime import datetime, timezone
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from scrappystats.log import configure_logging

configure_logging()

log = logging.getLogger("scrappystats.fetch")

BASE_URL = "https://stfc.pro/alliance/"


def fetch_alliance_page(alliance_id: str) -> str:
    url = BASE_URL + alliance_id
    log.info("Fetching %s", url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _parse_number(txt: str) -> int:
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


def parse_roster(html: str) -> Dict[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        raise RuntimeError("Roster table not found")

    roster: Dict[str, dict] = {}
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

        rss = _parse_number(tds[4].get_text(strip=True))
        iso = _parse_number(tds[5].get_text(strip=True))
        join_date = tds[6].get_text(strip=True)

        roster[name] = {
            "name": name,
            "rank": role,
            "level": level,
            "rss": rss,
            "iso": iso,
            "join_date": join_date,
        }

    return roster


def fetch_alliance_roster(alliance_id: str) -> List[dict]:
    html = fetch_alliance_page(alliance_id)
    roster = parse_roster(html)
    return list(roster.values())


def scrape_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
