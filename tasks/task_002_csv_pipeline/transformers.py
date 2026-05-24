"""Data transformation functions for the CSV pipeline."""
from __future__ import annotations

from typing import Any


def clean_row(row: dict[str, str]) -> dict[str, Any]:
    """Clean and type-coerce a single CSV row.

    Strips whitespace from strings, converts numeric fields to float/int.
    """
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        stripped = value.strip() if isinstance(value, str) else value
        # Attempt numeric conversion
        try:
            if "." in str(stripped):
                cleaned[key] = float(stripped)
            else:
                cleaned[key] = int(stripped)
        except (ValueError, TypeError):
            cleaned[key] = stripped
    return cleaned


def calculate_running_totals(
    rows: list[dict[str, Any]],
    amount_column: str = "amount",
) -> list[dict[str, Any]]:
    """Add a ``running_total`` field to each row.

    The running total is the cumulative sum of *amount_column* values.

    BUG: The accumulator starts at 0 but the first addition happens
    *after* assigning running_total, so the first row always gets
    running_total == 0 instead of the first row's amount.  Every
    subsequent row is off by the first row's amount.
    """
    accumulator: float = 0.0
    result: list[dict[str, Any]] = []

    for row in rows:
        new_row = dict(row)
        # BUG: assign BEFORE adding — first row gets 0.0
        new_row["running_total"] = accumulator
        accumulator += float(row[amount_column])
        result.append(new_row)

    return result


def filter_rows(
    rows: list[dict[str, Any]],
    column: str,
    value: Any,
) -> list[dict[str, Any]]:
    """Return only rows where *column* equals *value*."""
    return [r for r in rows if r.get(column) == value]
