from datetime import datetime, timezone
from pathlib import Path

from scrappystats.utils import load_json, history_snapshot_path, DATA_ROOT, HISTORY_DIR


STATE_DIR = DATA_ROOT / "state"

def load_state_and_baseline(alliance_id: str, kind: str):
    """
    Load current alliance state and the baseline snapshot used
    to compute report deltas.
    """
    state_path = STATE_DIR / f"{alliance_id}.json"
    baseline_path = HISTORY_DIR / kind / f"{alliance_id}.json"

    state = load_json(state_path, {})
    baseline = load_json(baseline_path, {})

    return state, baseline

def load_snapshots(alliance_id: str, start_ts: str, end_ts: str):
    """
    Load two historical snapshots for delta computation.
    """
    start = load_json(history_snapshot_path(alliance_id, start_ts), {})
    end = load_json(history_snapshot_path(alliance_id, end_ts), {})
    return start, end


def _parse_snapshot_ts(path: Path) -> datetime | None:
    try:
        return datetime.fromisoformat(path.stem.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_snapshot_at_or_before(alliance_id: str, target_dt: datetime) -> dict:
    """
    Load the most recent snapshot at or before the target timestamp.
    """
    history_dir = HISTORY_DIR / alliance_id
    if not history_dir.exists():
        return {}

    if target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=timezone.utc)

    best_path: Path | None = None
    best_ts: datetime | None = None
    for file in history_dir.glob("*.json"):
        ts = _parse_snapshot_ts(file)
        if ts is None or ts > target_dt:
            continue
        if best_ts is None or ts > best_ts:
            best_ts = ts
            best_path = file

    if best_path is None:
        return {}

    return load_json(best_path, {})


def load_snapshot_at_or_after(alliance_id: str, target_dt: datetime) -> dict:
    """
    Load the earliest snapshot at or after the target timestamp.
    """
    history_dir = HISTORY_DIR / alliance_id
    if not history_dir.exists():
        return {}

    if target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=timezone.utc)

    best_path: Path | None = None
    best_ts: datetime | None = None
    for file in history_dir.glob("*.json"):
        ts = _parse_snapshot_ts(file)
        if ts is None or ts < target_dt:
            continue
        if best_ts is None or ts < best_ts:
            best_ts = ts
            best_path = file

    if best_path is None:
        return {}

    return load_json(best_path, {})

def compute_deltas(cur: dict, prev: dict):
    deltas = {}
    for name, pdata in cur.items():
        c_helps = pdata.get("helps", 0)
        c_rss = pdata.get("rss", 0)
        c_iso = pdata.get("iso", 0)
        c_resources_mined = pdata.get("resources_mined", 0)
        prev_p = prev.get(name, {})
        d = {
            "helps": c_helps - prev_p.get("helps", 0),
            "rss": c_rss - prev_p.get("rss", 0),
            "iso": c_iso - prev_p.get("iso", 0),
            "resources_mined": c_resources_mined - prev_p.get("resources_mined", 0),
        }
        deltas[name] = d
    return deltas

def make_table(headers, rows, *, min_widths=None):
    """
    Build a fixed-width monospace table suitable for Discord code blocks.
    """
    if min_widths and len(min_widths) != len(headers):
        raise ValueError("min_widths must match headers length")

    def is_number(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    if not rows:
        rows = [["No data available."] + [""] * (len(headers) - 1)]

    widths = [len(h) for h in headers]
    if min_widths:
        widths = [max(widths[i], min_widths[i]) for i in range(len(headers))]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    numeric_cols = []
    for idx in range(len(headers)):
        column_values = [row[idx] for row in rows if idx < len(row)]
        numeric_cols.append(bool(column_values) and all(is_number(v) for v in column_values))

    def fmt_cell(cell, idx):
        text = str(cell)
        return text.rjust(widths[idx]) if numeric_cols[idx] else text.ljust(widths[idx])

    def fmt_row(row):
        return "  ".join(fmt_cell(cell, i) for i, cell in enumerate(row))

    header_line = fmt_row(headers)
    separator = "-" * len(header_line)
    lines = [header_line, separator]

    for row in rows:
        lines.append(fmt_row(row))

    return "\n".join(lines)


def build_table_from_rows(columns: list[dict], rows: list[dict]) -> str:
    """
    Build a fixed-width monospace table from column specs and row dicts.
    """
    headers = [column.get("label", "") for column in columns]
    keys = [column.get("key") for column in columns]
    min_widths = [column.get("min_width", 0) or 0 for column in columns]

    normalized_rows = []
    for row in rows:
        values = [row.get(key, "") for key in keys]
        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))
        elif len(values) > len(headers):
            values = values[:len(headers)]
        normalized_rows.append(values)

    widths = [len(str(header)) for header in headers]
    for row in normalized_rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(str(cell)))
    widths = [max(widths[i], min_widths[i]) for i in range(len(widths))]

    return make_table(headers, normalized_rows, min_widths=widths)
