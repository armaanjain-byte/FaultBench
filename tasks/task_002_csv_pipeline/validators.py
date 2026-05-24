"""Data validation helpers for the CSV pipeline."""
from __future__ import annotations

from typing import Any


def validate_row(row: dict[str, Any], required_columns: list[str]) -> list[str]:
    """Validate a single row of data.

    Returns a list of error messages (empty if the row is valid).
    """
    errors: list[str] = []
    for col in required_columns:
        if col not in row or row[col] is None or str(row[col]).strip() == "":
            errors.append(f"Missing or empty required column: {col}")
    return errors


def validate_numeric(value: Any, column_name: str) -> tuple[float, str | None]:
    """Attempt to coerce *value* to a float.

    Returns ``(parsed_value, None)`` on success or ``(0.0, error_message)``
    on failure.
    """
    try:
        return float(value), None
    except (ValueError, TypeError):
        return 0.0, f"Non-numeric value in column '{column_name}': {value!r}"


def validate_dataset(rows: list[dict[str, Any]], required_columns: list[str]) -> list[str]:
    """Validate an entire dataset.

    Returns a list of all validation errors across all rows.
    """
    all_errors: list[str] = []
    for idx, row in enumerate(rows):
        row_errors = validate_row(row, required_columns)
        for err in row_errors:
            all_errors.append(f"Row {idx + 1}: {err}")
    return all_errors
