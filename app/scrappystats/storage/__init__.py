from pathlib import Path

RAW_DIR = Path("/app/data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

def save_raw_html(alliance_tag: str, html: str):
    """Persist raw HTML for debugging/auditing."""
    path = RAW_DIR / f"{alliance_tag}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)

__all__ = ["save_raw_html"]
