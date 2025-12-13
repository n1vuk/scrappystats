import logging
import requests

from .utils import load_alliances
from .report_common import compute_deltas, load_state_and_baseline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def send_webhook(url: str, content: str):
    resp = requests.post(url, json={"content": content})
    if resp.status_code not in (200, 204):
        logging.error("Webhook failed: %s %s", resp.status_code, resp.text)

def main():
    logging.info("=== Interim report start ===")
    cfg = load_alliances()
    for alliance in cfg.get("alliances", []):
        aid = alliance["id"]
        name = alliance.get("name", aid)
        webhook = alliance.get("webhook")
        if not webhook:
            continue
        state, prev = load_state_and_baseline(aid, "daily")
        deltas = compute_deltas(state, prev)
        lines = []
        lines.append(f"📊 **Interim Contribution Report — {name}**")
        lines.append("_Since last daily snapshot_")
        helpers = sorted(deltas.items(), key=lambda kv: kv[1]["helps"], reverse=True)
        lines.append("")
        lines.append("🫡 **Top Helpers (interim)**")
        for player, d in helpers[:10]:
            if d["helps"] <= 0:
                continue
            lines.append(f"- {player}: {d['helps']} helps")
        send_webhook(webhook, "\n".join(lines))
    logging.info("=== Interim report complete ===")

if __name__ == "__main__":
    main()
