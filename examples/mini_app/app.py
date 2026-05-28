"""Tiny app that bootstraps from schema.sql and validates its structure."""

from __future__ import annotations

import re
from pathlib import Path


def validate_schema(project_dir: Path) -> str:
    """Read schema.sql and verify the expected ``users`` table exists.

    Returns the schema text on success.
    Raises RuntimeError if the file is missing or the table is not found.
    """
    schema_file = project_dir / "schema.sql"
    if not schema_file.exists():
        raise RuntimeError(f"schema.sql not found in {project_dir}")

    schema = schema_file.read_text()

    if not re.search(r"CREATE TABLE users\b", schema):
        raise RuntimeError(
            "Expected 'CREATE TABLE users' not found in schema.sql. "
            "Schema may have drifted."
        )

    return schema
