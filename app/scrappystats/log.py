import logging
import os
from typing import Optional

from .config import load_config

log = logging.getLogger("scrappystats")

DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


def _resolve_log_level() -> int:
    env_level = os.getenv("SCRAPPYSTATS_LOG_LEVEL")
    if env_level:
        return logging._nameToLevel.get(env_level.upper(), logging.INFO)

    cfg = load_config()
    level_name = cfg.get("logging", {}).get("level", "INFO")
    return logging._nameToLevel.get(str(level_name).upper(), logging.INFO)


def configure_logging(level: Optional[int] = None) -> None:
    resolved = level if level is not None else _resolve_log_level()
    logging.basicConfig(level=resolved, format=DEFAULT_LOG_FORMAT)
