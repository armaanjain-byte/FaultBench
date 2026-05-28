from __future__ import annotations

from pathlib import Path

from pytest_faultbench.mutations.base import BaseMutation


class ConfigDriftMutation(BaseMutation):
    """Rename ``DATABASE_URL`` to ``DB_URL`` in config.json."""

    def __init__(self) -> None:
        self._original: str | None = None

    def apply(self, work_dir: Path) -> None:
        config = work_dir / "config.json"
        if not config.exists():
            raise RuntimeError(f"config.json not found in {work_dir}")

        self._original = config.read_text()
        if "DATABASE_URL" not in self._original:
            raise RuntimeError("DATABASE_URL not found in config.json")

        config.write_text(self._original.replace("DATABASE_URL", "DB_URL"))

    def rollback(self, work_dir: Path) -> None:
        if self._original is None:
            return
        config = work_dir / "config.json"
        config.write_text(self._original)
        self._original = None
