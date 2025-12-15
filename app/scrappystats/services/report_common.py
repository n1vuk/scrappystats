from scrappystats.utils import load_json
from .legacy import state_path, history_snapshot_path

def compute_deltas(cur: dict, prev: dict):
    deltas = {}
    for name, pdata in cur.items():
        c_helps = pdata.get("helps", 0)
        c_rss = pdata.get("rss", 0)
        c_iso = pdata.get("iso", 0)
        prev_p = prev.get(name, {})
        d = {
            "helps": c_helps - prev_p.get("helps", 0),
            "rss": c_rss - prev_p.get("rss", 0),
            "iso": c_iso - prev_p.get("iso", 0),
        }
        deltas[name] = d
    return deltas

def load_state_and_baseline(alliance_id: str, kind: str):
    state = load_json(state_path(alliance_id), {})
    baseline = load_json(history_snapshot_path(alliance_id, kind), {})
    return state, baseline

def make_table(headers, rows):
    """
    Build a fixed-width monospace table suitable for Discord code blocks.
    """
    if not rows:
        return "No data available."

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def fmt_row(row):
        return " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))

    lines = [
        fmt_row(headers),
        "-+-".join("-" * w for w in widths),
    ]

    for row in rows:
        lines.append(fmt_row(row))

    return "\n".join(lines)
