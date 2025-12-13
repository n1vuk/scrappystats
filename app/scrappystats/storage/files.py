
import os

def data_dir():
    root = os.path.dirname(os.path.abspath(__file__))
    # parent of storage module is scrappystats/storage
    # data directory is scrappystats/data
    return os.path.join(os.path.dirname(root), "data")

def ensure_data_dir():
    d = data_dir()
    if not os.path.exists(d):
        os.makedirs(d)

def state_path(alliance_id: str):
    return os.path.join(data_dir(), f"alliance_{alliance_id}_state.json")
