"""JSON file-based storage for inventory data."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def _load_config() -> dict[str, Any]:
    with open("config.yaml", "r") as fh:
        return yaml.safe_load(fh)


def _get_storage_path() -> str:
    config = _load_config()
    return config.get("storage_path", "inventory_data.json")


def load_inventory(storage_path: str | None = None) -> list[dict[str, Any]]:
    """Load the inventory from the JSON file.

    Returns an empty list if the file does not exist.
    """
    path = storage_path or _get_storage_path()
    if not Path(path).exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        return []
    return data


def save_inventory(
    items: list[dict[str, Any]],
    storage_path: str | None = None,
) -> None:
    """Persist the inventory list to the JSON file."""
    path = storage_path or _get_storage_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=2, default=str)


def next_id(items: list[dict[str, Any]]) -> int:
    """Return the next available item ID."""
    if not items:
        return 1
    return max(item.get("id", 0) for item in items) + 1
