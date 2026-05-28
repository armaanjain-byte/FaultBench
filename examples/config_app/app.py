from __future__ import annotations

import json
from pathlib import Path


def load_config(project_dir: Path | None = None) -> dict[str, str]:
    config_file = (project_dir or Path(__file__).parent) / "config.json"
    with config_file.open() as f:
        return json.load(f)


def get_database_url(project_dir: Path | None = None) -> str:
    config = load_config(project_dir)
    try:
        return config["DATABASE_URL"]
    except KeyError as exc:
        raise RuntimeError("DATABASE_URL missing from config.json") from exc
