from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseMutation(ABC):
    @abstractmethod
    def apply(self, work_dir: Path) -> None: ...

    @abstractmethod
    def rollback(self, work_dir: Path) -> None: ...
