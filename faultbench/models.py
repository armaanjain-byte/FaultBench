"""Typed data models used across FaultBench.

Every data structure that crosses a module boundary is defined here as a
frozen dataclass with full type annotations.  No untyped dicts should
ever be passed between subsystems — use these models instead.
"""

from __future__ import annotations

import dataclasses
import time
import uuid
from typing import Optional

from faultbench.constants import AgentName, MutationTiming, MutationType, RunStatus


# ---------------------------------------------------------------------------
# Run record — one row per benchmark execution
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class RunRecord:
    """Immutable record for a single benchmark run, maps 1:1 to the ``runs``
    table in SQLite.
    """

    run_id: str
    task_name: str
    agent_name: str
    mutation_type: Optional[str]  # None ⇒ clean baseline
    mutation_timing: Optional[str]  # "before" in v1
    success: bool
    retry_count: int
    runtime_seconds: float
    tokens_used: Optional[int]
    exception_count: int
    first_failure_step: Optional[int]
    raw_log_path: Optional[str]
    created_at: float  # UNIX timestamp

    @staticmethod
    def create(
        *,
        task_name: str,
        agent_name: str,
        mutation_type: Optional[MutationType] = None,
        mutation_timing: Optional[MutationTiming] = None,
        success: bool,
        retry_count: int,
        runtime_seconds: float,
        tokens_used: Optional[int] = None,
        exception_count: int = 0,
        first_failure_step: Optional[int] = None,
        raw_log_path: Optional[str] = None,
    ) -> RunRecord:
        """Factory that auto-generates ``run_id`` and ``created_at``."""
        return RunRecord(
            run_id=uuid.uuid4().hex,
            task_name=task_name,
            agent_name=agent_name,
            mutation_type=str(mutation_type) if mutation_type else None,
            mutation_timing=str(mutation_timing) if mutation_timing else None,
            success=success,
            retry_count=retry_count,
            runtime_seconds=runtime_seconds,
            tokens_used=tokens_used,
            exception_count=exception_count,
            first_failure_step=first_failure_step,
            raw_log_path=raw_log_path,
            created_at=time.time(),
        )


# ---------------------------------------------------------------------------
# Task configuration — loaded from each task's task.yaml
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class TaskConfig:
    """Metadata and execution instructions for a benchmark task."""

    name: str
    description: str
    instruction: str  # what the agent is told to do
    repo_path: str  # absolute path to the task directory
    verify_command: str  # command to check if the task was completed
    valid_mutations: list[MutationType]
    timeout_seconds: int = 900


# ---------------------------------------------------------------------------
# Mutation specification — from mutations.yaml per task
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class MutationAction:
    """A single atomic mutation step (e.g., rename a column, delete a file)."""

    action: str  # e.g., "rename_column", "delete_file", "change_version"
    target: str  # file or resource being mutated
    details: dict[str, str]  # action-specific parameters


@dataclasses.dataclass(frozen=True)
class MutationSpec:
    """Full specification for a mutation applied to a specific task.

    Loaded from the task's ``mutations.yaml``.
    """

    mutation_type: MutationType
    description: str
    causal_path: str  # why this mutation affects the task
    actions: list[MutationAction]
    rollback_actions: list[MutationAction]  # how to undo the mutation


# ---------------------------------------------------------------------------
# Benchmark configuration — loaded from config.yaml
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class AgentConfig:
    """Configuration for the coding agent."""

    default: str = "openhands"
    model: str = "claude-sonnet-4-20250514"
    max_iterations: int = 30
    poll_interval_seconds: float = 5.0


@dataclasses.dataclass
class SandboxConfig:
    """Docker sandbox resource constraints."""

    image: str = "faultbench-sandbox:latest"
    memory_limit: str = "512m"
    cpu_quota: int = 50_000
    max_runtime_seconds: int = 900


@dataclasses.dataclass
class PathsConfig:
    """File system paths for generated artifacts."""

    db: str = "db/faultbench.db"
    logs: str = "logs/"
    reports: str = "reports/"
    tasks: str = "tasks/"


@dataclasses.dataclass
class BenchmarkSettings:
    """Benchmark execution parameters."""

    min_runs_for_comparison: int = 5
    default_runs: int = 10


@dataclasses.dataclass
class BenchmarkConfig:
    """Top-level configuration loaded from ``config.yaml``.

    This is the single typed configuration object threaded through the
    entire application.
    """

    agent: AgentConfig = dataclasses.field(default_factory=AgentConfig)
    sandbox: SandboxConfig = dataclasses.field(default_factory=SandboxConfig)
    paths: PathsConfig = dataclasses.field(default_factory=PathsConfig)
    benchmark: BenchmarkSettings = dataclasses.field(default_factory=BenchmarkSettings)


# ---------------------------------------------------------------------------
# Metrics aggregation — used by comparator / reporting
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class AggregatedMetrics:
    """Aggregated metrics over multiple runs of the same condition."""

    condition_label: str  # e.g., "baseline" or "schema_drift"
    total_runs: int
    success_count: int
    success_rate: float
    mean_runtime_seconds: float
    median_runtime_seconds: float
    mean_retry_count: float
    mean_exception_count: float
    mean_tokens_used: Optional[float]
    mean_first_failure_step: Optional[float]


@dataclasses.dataclass(frozen=True)
class DegradationReport:
    """Comparison between baseline and mutated condition for one task."""

    task_name: str
    mutation_type: str
    baseline: AggregatedMetrics
    mutated: AggregatedMetrics
    success_rate_delta: float  # negative means degradation
    runtime_overhead_ratio: float  # >1.0 means slower
    retry_overhead_ratio: float
