"""Persisted user preferences (last URL, server, output folder, slide search dirs).

The JSON file lives next to the package (the project directory when run from source).
Override the location with the CONNECT2MP4_HOME environment variable.
"""
import json
import os

APP_DIR = os.environ.get("CONNECT2MP4_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(APP_DIR, ".connect2mp4.json")


def load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass
