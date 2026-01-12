import logging
import os
from pathlib import Path
from typing import Optional

from .config import load_config

log = logging.getLogger("scrappystats")

DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DEFAULT_LOG_DIR = Path(os.getenv("SCRAPPYSTATS_LOG_DIR", "/logs"))


def _resolve_log_level() -> int:
    env_level = os.getenv("SCRAPPYSTATS_LOG_LEVEL")
    if env_level:
        return logging._nameToLevel.get(env_level.upper(), logging.INFO)

    cfg = load_config()
    level_name = cfg.get("logging", {}).get("level", "INFO")
    return logging._nameToLevel.get(str(level_name).upper(), logging.INFO)


def configure_logging(level: Optional[int] = None) -> None:
    resolved = level if level is not None else _resolve_log_level()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(DEFAULT_LOG_DIR / "scrappystats.log")
        handlers.append(file_handler)
    except OSError:
        log.warning("Failed to initialize log file in %s", DEFAULT_LOG_DIR)

    logging.basicConfig(level=resolved, format=DEFAULT_LOG_FORMAT, handlers=handlers)

    detail_logger = logging.getLogger("scrappystats.member_detail_payload")
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith("member_detail.log")
               for h in detail_logger.handlers):
        try:
            detail_handler = logging.FileHandler(DEFAULT_LOG_DIR / "member_detail.log")
            detail_handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
            detail_handler.setLevel(logging.DEBUG)
            detail_logger.addHandler(detail_handler)
            detail_logger.setLevel(logging.DEBUG)
            detail_logger.propagate = False
        except OSError:
            log.warning("Failed to initialize member detail log file in %s", DEFAULT_LOG_DIR)
