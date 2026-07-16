import os
from importlib.resources import files
from pathlib import Path


import yaml


def load_config(config_path=None):
    explicit_path = config_path or os.getenv("FUNDMASTER_CONFIG_PATH")
    candidate = Path(explicit_path) if explicit_path else Path("config/default.yaml")
    if candidate.exists():
        return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}

    packaged = files("src.resources").joinpath("default.yaml")
    return yaml.safe_load(packaged.read_text(encoding="utf-8")) or {}


config = load_config()
