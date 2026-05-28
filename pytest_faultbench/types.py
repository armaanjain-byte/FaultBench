from __future__ import annotations

import enum
from dataclasses import dataclass


class MutationType(enum.Enum):
    SCHEMA_DRIFT = "schema_drift"


@dataclass
class MutationResult:
    mutation_type: str
    task_dir: str
    work_dir: str
    applied: bool
    rolled_back: bool
    error: str | None
