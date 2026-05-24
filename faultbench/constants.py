"""Centralized constants, enums, and static configuration for FaultBench.

All magic strings, mutation types, agent identifiers, and run statuses
are defined here so that the rest of the codebase references a single
source of truth.
"""

from __future__ import annotations

import enum


class MutationType(str, enum.Enum):
    """Controlled environmental mutations injected before agent execution.

    Each value maps to a concrete mutation implementation in
    ``faultbench.mutations``.
    """

    SCHEMA_DRIFT = "schema_drift"
    DEPENDENCY_DRIFT = "dependency_drift"
    CONFIG_CORRUPTION = "config_corruption"
    MISSING_FILE = "missing_file"
    API_CONTRACT_DRIFT = "api_contract_drift"

    def __str__(self) -> str:
        return self.value


class AgentName(str, enum.Enum):
    """Supported autonomous coding agents."""

    OPENHANDS = "openhands"

    def __str__(self) -> str:
        return self.value


class RunStatus(str, enum.Enum):
    """Outcome status of a single benchmark run."""

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    TIMEOUT = "timeout"

    def __str__(self) -> str:
        return self.value


class MutationTiming(str, enum.Enum):
    """When the mutation is applied relative to agent execution.

    v1 supports only ``BEFORE``. ``DURING`` is reserved for v2.
    """

    BEFORE = "before"

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Static defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH: str = "config.yaml"
DEFAULT_DB_PATH: str = "db/faultbench.db"
DEFAULT_LOG_DIR: str = "logs"
DEFAULT_REPORT_DIR: str = "reports"
DEFAULT_TASKS_DIR: str = "tasks"

# Docker defaults
DEFAULT_SANDBOX_IMAGE: str = "faultbench-sandbox:latest"
DEFAULT_MEMORY_LIMIT: str = "512m"
DEFAULT_CPU_QUOTA: int = 50_000  # 50 % of one core
DEFAULT_MAX_RUNTIME_SECONDS: int = 900  # 15-minute hard cap

# Agent defaults
DEFAULT_MAX_ITERATIONS: int = 30
DEFAULT_POLL_INTERVAL: float = 5.0
DEFAULT_MODEL: str = "claude-sonnet-4-20250514"

# Benchmark defaults
MIN_RUNS_FOR_COMPARISON: int = 5
DEFAULT_RUNS: int = 10

# Log parsing
TRACEBACK_MARKER: str = "Traceback (most recent call last):"
