"""Fetch alliance roster data from STFC.pro (v2 pipeline)."""
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scrappystats.log import configure_logging
from scrappystats.utils import save_raw_html, save_raw_json

configure_logging()

log = logging.getLogger("scrappystats.fetch")

BASE_URL = "https://stfc.pro/alliance/"
ROOT_URL = "https://stfc.pro"


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


def _normalize_label(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(cleaned.split())


def _next_numeric_text(node) -> str | None:
    current = node
    for _ in range(40):
        current = getattr(current, "next_element", None)
        if current is None:
            break
        if isinstance(current, str):
            text = current.strip()
        else:
            text = current.get_text(strip=True) if hasattr(current, "get_text") else ""
        if text and any(ch.isdigit() for ch in text):
            return text
    return None


def _extract_stat_value(soup: BeautifulSoup, labels: tuple[str, ...]) -> int | None:
    label_set = {_normalize_label(label) for label in labels}
    for text_node in soup.find_all(string=True):
        label = text_node.strip()
        if not label:
            continue
        if _normalize_label(label) in label_set:
            value_text = _next_numeric_text(text_node)
            if value_text:
                return _parse_number(value_text)
    return None


def parse_member_stats(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    stats = {
        "power": _extract_stat_value(soup, ("power",)),
        "max_power": _extract_stat_value(soup, ("max power", "max. power")),
        "power_destroyed": _extract_stat_value(soup, ("power destroyed",)),
        "arena_rating": _extract_stat_value(soup, ("arena rating",)),
        "assessment_rank": _extract_stat_value(soup, ("assessment rank",)),
        "missions_completed": _extract_stat_value(soup, ("missions completed",)),
        "resources_mined": _extract_stat_value(soup, ("resources mined",)),
        "alliance_helps_sent": _extract_stat_value(soup, ("alliance helps sent",)),
    }
    return {key: value for key, value in stats.items() if value is not None}


def fetch_member_detail_html(detail_url: str) -> str:
    url = detail_url
    if not detail_url.startswith("http"):
        url = urljoin(ROOT_URL, detail_url)
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


def fetch_member_stats(detail_url: str) -> dict:
    html = fetch_member_detail_html(detail_url)
    return parse_member_stats(html)


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


def _extract_detail_url(cell) -> str | None:
    link = cell.find("a", href=True)
    if not link:
        return None
    href = link.get("href")
    if not href:
        return None
    return urljoin(ROOT_URL, href)


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

        name_cell = tds[1]
        name_span = name_cell.find("span", class_="cursor-pointer")
        if not name_span:
            continue
        name = name_span.get_text(strip=True)
        if not name:
            continue
        detail_url = _extract_detail_url(name_cell)

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
            "detail_url": detail_url,
        }

    return roster


def _member_sample_stamp(scrape_stamp: str, member_name: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", member_name).strip("_") or "member"
    return f"{scrape_stamp}_member_{safe_name}"


def fetch_alliance_roster(
    alliance_id: str,
    *,
    debug: bool = False,
    scrape_stamp: str | None = None,
) -> List[dict]:
    html = fetch_alliance_page(alliance_id)
    if debug:
        try:
            path = save_raw_html(alliance_id, html)
            log.info("Saved raw HTML to %s", path)
        except Exception:
            log.exception("Failed to save raw HTML for alliance %s", alliance_id)
    roster = parse_roster(html)
    members = list(roster.values())
    saved_sample = False
    for member in members:
        detail_url = member.get("detail_url")
        if not detail_url:
            continue
        try:
            if not saved_sample and scrape_stamp:
                detail_html = fetch_member_detail_html(detail_url)
                detail_stats = parse_member_stats(detail_html)
                sample_stamp = _member_sample_stamp(scrape_stamp, member.get("name", "member"))
                save_raw_html(alliance_id, detail_html, stamp=sample_stamp)
                sample_payload = {**member, **detail_stats}
                save_raw_json(alliance_id, sample_payload, stamp=sample_stamp)
                saved_sample = True
            else:
                detail_stats = fetch_member_stats(detail_url)
        except Exception:
            log.exception("Failed to fetch member stats: %s", detail_url)
            continue
        if detail_stats:
            member.update(detail_stats)
            if detail_stats.get("max_power") is not None:
                member["power"] = detail_stats["max_power"]
    return members


def scrape_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
