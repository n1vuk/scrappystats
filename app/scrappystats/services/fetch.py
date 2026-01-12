"""Fetch alliance roster data from STFC.pro (v2 pipeline)."""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
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


def _coerce_int(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return _parse_number(value)
    return None


def _find_payload_candidate(payload: dict) -> dict:
    for key in ("player", "data", "result", "playerDetails", "details"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _payload_value(payload: dict, *keys: str):
    lower_map = {
        key.lower(): key
        for key in payload.keys()
        if isinstance(key, str)
    }
    for key in keys:
        mapped = lower_map.get(key.lower())
        if mapped is not None:
            return payload.get(mapped)
    return None


def parse_member_details_payload(payload: dict) -> dict:
    candidate = _find_payload_candidate(payload)
    stats = {
        "power": _coerce_int(_payload_value(candidate, "power")),
        "max_power": _coerce_int(_payload_value(candidate, "maxPower", "max_power")),
        "power_destroyed": _coerce_int(_payload_value(candidate, "powerDestroyed", "power_destroyed")),
        "arena_rating": _coerce_int(_payload_value(candidate, "arenaRating", "arena_rating")),
        "assessment_rank": _coerce_int(_payload_value(candidate, "assessmentRank", "assessment_rank")),
        "missions_completed": _coerce_int(_payload_value(candidate, "missionsCompleted", "missions_completed")),
        "resources_mined": _coerce_int(_payload_value(candidate, "resourcesMined", "resources_mined")),
        "alliance_helps_sent": _coerce_int(
            _payload_value(candidate, "allianceHelpsSent", "alliance_helps_sent")
        ),
    }
    return {key: value for key, value in stats.items() if value is not None}


def fetch_member_details_api(player_id: str) -> Tuple[dict, Optional[dict]]:
    url = f"{ROOT_URL}/api/playerDetails?playerid={player_id}"
    resp = requests.get(
        url,
        timeout=30,
        headers={
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    return parse_member_details_payload(payload), payload


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

def _extract_nuxt_payload(html: str) -> list | None:
    match = re.search(
        r'<script[^>]+id="__NUXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return None
    raw = match.group(1)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, list) else None


def _extract_player_ids_from_nuxt(html: str) -> dict[str, str]:
    payload = _extract_nuxt_payload(html)
    if not payload:
        return {}
    name_to_id: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict) or "playerid" not in item:
            continue
        pid_idx = item.get("playerid")
        name_idx = item.get("owner") if "owner" in item else item.get("name")
        if not isinstance(pid_idx, int) or not isinstance(name_idx, int):
            continue
        if pid_idx >= len(payload) or name_idx >= len(payload):
            continue
        pid_val = payload[pid_idx]
        name_val = payload[name_idx]
        if not isinstance(pid_val, int) or not isinstance(name_val, str):
            continue
        name_to_id[name_val] = str(pid_val)
    return name_to_id


def _extract_player_id(detail_url: str | None) -> str | None:
    if not detail_url:
        return None
    match = re.search(r"/player/(\d+)", detail_url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]playerid=(\d+)", detail_url)
    if match:
        return match.group(1)
    return None


def _extract_player_id_from_attrs(*nodes) -> str | None:
    attr_keys = (
        "data-player-id",
        "data-playerid",
        "data-player",
        "data-id",
        "playerid",
        "player-id",
    )
    for node in nodes:
        if not node or not hasattr(node, "attrs"):
            continue
        for key in attr_keys:
            raw = node.attrs.get(key)
            if not raw:
                continue
            match = re.search(r"\d+", str(raw))
            if match:
                return match.group(0)
    return None


def parse_roster(html: str) -> Dict[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        raise RuntimeError("Roster table not found")

    headers = _header_cells(table)
    nuxt_player_ids = _extract_player_ids_from_nuxt(html)

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
        player_id = _extract_player_id(detail_url) or _extract_player_id_from_attrs(name_cell, tr)
        if not player_id:
            player_id = nuxt_player_ids.get(name)

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
            "player_id": player_id,
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
        player_id = member.get("player_id")
        if not detail_url and not player_id:
            continue
        try:
            if player_id:
                detail_stats, detail_payload = fetch_member_details_api(player_id)
                if not saved_sample and scrape_stamp:
                    sample_stamp = _member_sample_stamp(scrape_stamp, member.get("name", "member"))
                    if detail_payload is not None:
                        save_raw_json(alliance_id, detail_payload, stamp=sample_stamp)
                    sample_payload = {**member, **detail_stats}
                    save_raw_json(alliance_id, sample_payload, stamp=f"{sample_stamp}_member")
                    saved_sample = True
            elif not saved_sample and scrape_stamp:
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
            target = detail_url or f"player_id={player_id}"
            log.exception("Failed to fetch member stats: %s", target)
            continue
        if detail_stats:
            member.update(detail_stats)
            if detail_stats.get("max_power") is not None:
                member["power"] = detail_stats["max_power"]
    return members


def scrape_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
