"""Loading of YAML/JSON data files."""
from __future__ import annotations

from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"


def load_yaml(name: str, data_dir: Path = DATA_DIR) -> dict:
    with open(data_dir / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(data_dir: Path = DATA_DIR) -> dict:
    return load_yaml("config.yaml", data_dir)


def load_spec_defs(data_dir: Path = DATA_DIR) -> dict:
    return load_yaml("spec_defs.yaml", data_dir)
