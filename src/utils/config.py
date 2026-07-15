import yaml
import os
from pathlib import Path

def load_config():
    config_path = Path("config/default.yaml")
    if not config_path.exists():
        return {}
    
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

config = load_config()
