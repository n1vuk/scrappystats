
import os

DATA_ROOT = os.environ.get("SCRAPPYSTATS_DATA_ROOT", "/data")

def data_dir():
    return DATA_ROOT

def ensure_data_dir():
    d = data_dir()
    if not os.path.exists(d):
        os.makedirs(d)

def state_path(alliance_id: str):
    return os.path.join(data_dir(), f"alliance_{alliance_id}_state.json")
