import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

ALLIANCES_PATH = Path("/app/config/alliances.json")

# def load_alliances():
#     if not ALLIANCES_PATH.exists():
#         log.critical("FATAL: Alliances config not found: %s", ALLIANCES_PATH)
#         raise SystemExit(1)

#     try:
#         with ALLIANCES_PATH.open() as f:
#             return json.load(f)
#     except Exception as e:
#         log.critical("FATAL: Failed to load alliances config: %s", e)
#         raise SystemExit(1)

#Fix load alliances str vs load alliance object

def load_alliances():
    if not ALLIANCES_PATH.exists():
        log.critical("FATAL: Alliances config not found: %s", ALLIANCES_PATH)
        raise SystemExit(1)

    try:
        with ALLIANCES_PATH.open() as f:
            data = json.load(f)

        alliances = data.get("alliances")
        if not isinstance(alliances, list):
            raise ValueError("'alliances' must be a list")

        return alliances

    except Exception as e:
        log.critical("FATAL: Failed to load alliances config: %s", e)
        raise SystemExit(1)