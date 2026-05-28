from __future__ import annotations

from pathlib import Path

from pytest_faultbench.mutations.base import BaseMutation


class SchemaDriftMutation(BaseMutation):
    """Rename ``users`` to ``users_v2`` in schema.sql."""

    def __init__(self) -> None:
        self._original: str | None = None

    def apply(self, work_dir: Path) -> None:
        import re

        schema = work_dir / "schema.sql"
        if not schema.exists():
            raise RuntimeError(f"schema.sql not found in {work_dir}")

        self._original = schema.read_text()
        new_schema = re.sub(r"\busers\b", "users_v2", self._original)
        schema.write_text(new_schema)

    def rollback(self, work_dir: Path) -> None:
        if self._original is None:
            return
        schema = work_dir / "schema.sql"
        schema.write_text(self._original)
        self._original = None
