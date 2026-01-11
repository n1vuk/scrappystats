"""Fetch alliance roster data from STFC.pro (v2 pipeline)."""
import logging
from datetime import datetime, timezone
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from scrappystats.log import configure_logging
from scrappystats.utils import save_raw_html

configure_logging()

log = logging.getLogger("scrappystats.fetch")

BASE_URL = "https://stfc.pro/alliance/"


def fetch_alliance_page(alliance_id: str) -> str:
    url = BASE_URL + alliance_id
    log.info("Fetching %s", url)
    resp = requests.get(
        url,
        timeout=30,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
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


def _header_cells(table) -> list[str]:
    header_row = None
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
    if not header_row:
        header_row = table.find("tr")
    if not header_row:
        return []
    return [
        cell.get_text(strip=True).lower()
        for cell in header_row.find_all(["th", "td"])
    ]


def _find_header_index(headers: list[str], keys: tuple[str, ...]) -> int | None:
    for idx, header in enumerate(headers):
        if not header:
            continue
        for key in keys:
            if key in header:
                return idx
    return None


def _cell_text(
    cells,
    headers: list[str],
    keys: tuple[str, ...],
    *,
    fallback_idx: int | None = None,
    fallback_last: bool = False,
) -> str | None:
    idx = _find_header_index(headers, keys)
    if idx is not None and 0 <= idx < len(cells):
        return cells[idx].get_text(strip=True)
    if fallback_last and cells:
        return cells[-1].get_text(strip=True)
    if fallback_idx is not None and fallback_idx < len(cells):
        return cells[fallback_idx].get_text(strip=True)
    return None


def parse_roster(html: str) -> Dict[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        raise RuntimeError("Roster table not found")

    headers = _header_cells(table)

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

        power_text = _cell_text(
            tds,
            headers,
            ("power", "pwr"),
        )
        power = _parse_number(power_text) if power_text else 0

        helps_text = _cell_text(
            tds,
            headers,
            ("helps", "help"),
            fallback_idx=4 if len(tds) >= 8 else None,
        )
        has_helps = helps_text is not None
        helps = _parse_number(helps_text) if has_helps else 0
        rss = _parse_number(
            _cell_text(
                tds,
                headers,
                ("rss", "resources", "resource"),
                fallback_idx=5 if has_helps else 4,
            )
            or ""
        )
        iso = _parse_number(
            _cell_text(
                tds,
                headers,
                ("iso", "isogen"),
                fallback_idx=6 if has_helps else 5,
            )
            or ""
        )
        join_date = (
            _cell_text(
                tds,
                headers,
                ("join date", "joined", "join"),
                fallback_idx=7 if has_helps else 6,
                fallback_last=True,
            )
            or ""
        )

        roster[name] = {
            "name": name,
            "rank": role,
            "level": level,
            "power": power,
            "helps": helps,
            "rss": rss,
            "iso": iso,
            "join_date": join_date,
        }

    return roster


def fetch_alliance_roster(alliance_id: str, debug: bool = False) -> List[dict]:
    html = fetch_alliance_page(alliance_id)
    if debug:
        try:
            path = save_raw_html(alliance_id, html)
            log.info("Saved raw HTML to %s", path)
        except Exception:
            log.exception("Failed to save raw HTML for alliance %s", alliance_id)
    roster = parse_roster(html)
    return list(roster.values())


def scrape_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
