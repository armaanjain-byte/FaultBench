"""Metrics collection and aggregation for FaultBench.

Transforms raw agent results and parsed logs into structured
:class:`RunRecord` objects ready for database storage, and aggregates
multiple run records into :class:`AggregatedMetrics` for comparison.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Optional

from faultbench.agent.base import AgentResult
from faultbench.constants import MutationTiming, MutationType
from faultbench.logging import get_logger
from faultbench.metrics.log_parser import ParsedLogMetrics, parse_log_text
from faultbench.models import AggregatedMetrics, RunRecord

log = get_logger(__name__)


def collect_run_record(
    *,
    task_name: str,
    agent_name: str,
    agent_result: AgentResult,
    runtime_seconds: float,
    mutation_type: Optional[MutationType] = None,
    mutation_timing: Optional[MutationTiming] = None,
    raw_log_path: Optional[str] = None,
) -> RunRecord:
    """Build a :class:`RunRecord` from an agent result and parsed logs.

    This is the central point where raw agent output is transformed into
    a structured database record.

    Args:
        task_name: Name of the benchmark task.
        agent_name: Name of the agent that executed the task.
        agent_result: Result returned by the agent.
        runtime_seconds: Wall-clock execution time.
        mutation_type: Type of mutation applied (``None`` for baseline).
        mutation_timing: When the mutation was applied.
        raw_log_path: Path where the raw log was saved.

    Returns:
        A fully populated :class:`RunRecord`.
    """
    log.info(
        "collect_run_record",
        task=task_name,
        agent=agent_name,
        success=agent_result.success,
        mutation=str(mutation_type) if mutation_type else "baseline",
    )

    # Parse the raw output for exception metrics
    parsed = parse_log_text(agent_result.raw_output)

    record = RunRecord.create(
        task_name=task_name,
        agent_name=agent_name,
        mutation_type=mutation_type,
        mutation_timing=mutation_timing,
        success=agent_result.success,
        retry_count=agent_result.iterations_used,
        runtime_seconds=runtime_seconds,
        tokens_used=agent_result.tokens_used,
        exception_count=parsed.exception_count,
        first_failure_step=parsed.first_failure_step,
        raw_log_path=raw_log_path,
    )

    log.info(
        "run_record_created",
        run_id=record.run_id,
        exception_count=record.exception_count,
        first_failure_step=record.first_failure_step,
    )

    return record


def aggregate_runs(
    runs: list[RunRecord], condition_label: str
) -> AggregatedMetrics:
    """Aggregate multiple run records into summary statistics.

    Args:
        runs: List of run records for the same condition.
        condition_label: Human-readable label (e.g., "baseline",
                         "schema_drift").

    Returns:
        Aggregated metrics over all runs.

    Raises:
        ValueError: If the run list is empty.
    """
    if not runs:
        raise ValueError(f"Cannot aggregate empty run list for '{condition_label}'")

    total = len(runs)
    successes = sum(1 for r in runs if r.success)
    runtimes = [r.runtime_seconds for r in runs]
    retries = [r.retry_count for r in runs]
    exceptions = [r.exception_count for r in runs]

    # Token usage may be None for some runs
    token_values = [r.tokens_used for r in runs if r.tokens_used is not None]
    mean_tokens = statistics.mean(token_values) if token_values else None

    # First failure step may be None (no failure)
    failure_steps = [
        r.first_failure_step for r in runs if r.first_failure_step is not None
    ]
    mean_first_failure = (
        statistics.mean(failure_steps) if failure_steps else None
    )

    metrics = AggregatedMetrics(
        condition_label=condition_label,
        total_runs=total,
        success_count=successes,
        success_rate=successes / total,
        mean_runtime_seconds=statistics.mean(runtimes),
        median_runtime_seconds=statistics.median(runtimes),
        mean_retry_count=statistics.mean(retries),
        mean_exception_count=statistics.mean(exceptions),
        mean_tokens_used=mean_tokens,
        mean_first_failure_step=mean_first_failure,
    )

    log.info(
        "metrics_aggregated",
        condition=condition_label,
        total_runs=total,
        success_rate=round(metrics.success_rate, 3),
        mean_runtime=round(metrics.mean_runtime_seconds, 2),
    )

    return metrics


def save_raw_log(
    log_content: str,
    log_dir: Path,
    task_name: str,
    run_id: str,
) -> Path:
    """Save raw agent output to a log file.

    Args:
        log_content: The raw text to save.
        log_dir: Base directory for logs.
        task_name: Task name for subdirectory.
        run_id: Unique run identifier for the filename.

    Returns:
        Path to the saved log file.
    """
    task_log_dir = log_dir / task_name
    task_log_dir.mkdir(parents=True, exist_ok=True)

    log_path = task_log_dir / f"{run_id}.log"
    log_path.write_text(log_content, encoding="utf-8")

    log.info("raw_log_saved", path=str(log_path), size_bytes=len(log_content.encode("utf-8")))
    return log_path
