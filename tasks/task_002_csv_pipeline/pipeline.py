"""Main data-processing pipeline: CSV → clean → transform → JSON."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from transformers import clean_row, calculate_running_totals
from validators import validate_dataset


def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    """Load pipeline configuration from a YAML file."""
    with open(config_path, "r") as fh:
        return yaml.safe_load(fh)


def read_csv(file_path: str) -> list[dict[str, str]]:
    """Read a CSV file and return a list of row dictionaries."""
    rows: list[dict[str, str]] = []
    with open(file_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))
    return rows


def write_json(data: list[dict[str, Any]], file_path: str) -> None:
    """Write a list of dictionaries to a JSON file."""
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)


def run_pipeline(config_path: str = "config.yaml") -> list[dict[str, Any]]:
    """Execute the full pipeline and return the transformed rows.

    Steps:
        1. Load configuration
        2. Read CSV input
        3. Clean each row (type coercion, whitespace stripping)
        4. Validate required columns
        5. Compute running totals
        6. Write JSON output
    """
    config = load_config(config_path)

    input_path: str = config["input_path"]
    output_path: str = config["output_path"]

    # Step 1 — read
    raw_rows = read_csv(input_path)

    # Step 2 — clean
    cleaned_rows = [clean_row(row) for row in raw_rows]

    # Step 3 — validate
    required = list(config.get("column_mappings", {}).keys())
    errors = validate_dataset(cleaned_rows, required)
    if errors:
        raise ValueError(f"Validation failed with {len(errors)} errors: {errors}")

    # Step 4 — transform
    if config.get("include_running_totals", False):
        transformed_rows = calculate_running_totals(cleaned_rows)
    else:
        transformed_rows = cleaned_rows

    # Step 5 — write
    write_json(transformed_rows, output_path)

    return transformed_rows


if __name__ == "__main__":
    results = run_pipeline()
    print(f"Pipeline complete — {len(results)} rows written.")
