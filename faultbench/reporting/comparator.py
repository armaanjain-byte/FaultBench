"""Baseline vs. mutated comparison engine for FaultBench.

Computes degradation metrics by comparing baseline (clean) runs against
mutated runs for each task.  This is the analytical core of the
reporting pipeline.
"""

from __future__ import annotations

from typing import Optional

from faultbench.constants import MIN_RUNS_FOR_COMPARISON
from faultbench.db.store import BenchmarkStore
from faultbench.logging import get_logger
from faultbench.metrics.collector import aggregate_runs
from faultbench.models import AggregatedMetrics, DegradationReport

log = get_logger(__name__)


class InsufficientDataError(Exception):
    """Raised when there are too few runs to produce a valid comparison."""


def compare_task_mutation(
    store: BenchmarkStore,
    task_name: str,
    mutation_type: str,
    *,
    agent_name: Optional[str] = None,
    min_runs: int = MIN_RUNS_FOR_COMPARISON,
) -> DegradationReport:
    """Compare baseline and mutated runs for a single task + mutation.

    Args:
        store: Database access object.
        task_name: The benchmark task to compare.
        mutation_type: The mutation type to compare against baseline.
        agent_name: Optional filter by agent.
        min_runs: Minimum number of runs required per condition.

    Returns:
        A :class:`DegradationReport` with computed deltas.

    Raises:
        InsufficientDataError: If either condition has fewer than
            ``min_runs`` runs.
    """
    log.info(
        "comparison_start",
        task=task_name,
        mutation=mutation_type,
        agent=agent_name or "all",
    )

    # Fetch runs
    baseline_runs = store.get_baseline_runs(task_name, agent_name)
    mutated_runs = store.get_mutated_runs(task_name, mutation_type, agent_name)

    # Validate minimum data requirements
    if len(baseline_runs) < min_runs:
        raise InsufficientDataError(
            f"Task '{task_name}' has {len(baseline_runs)} baseline runs, "
            f"need at least {min_runs}. Run more baseline benchmarks first."
        )
    if len(mutated_runs) < min_runs:
        raise InsufficientDataError(
            f"Task '{task_name}' has {len(mutated_runs)} '{mutation_type}' runs, "
            f"need at least {min_runs}. Run more mutated benchmarks first."
        )

    # Aggregate
    baseline_metrics = aggregate_runs(baseline_runs, "baseline")
    mutated_metrics = aggregate_runs(mutated_runs, mutation_type)

    # Compute deltas
    success_delta = mutated_metrics.success_rate - baseline_metrics.success_rate

    runtime_ratio = (
        mutated_metrics.mean_runtime_seconds / baseline_metrics.mean_runtime_seconds
        if baseline_metrics.mean_runtime_seconds > 0
        else 1.0
    )

    retry_ratio = (
        mutated_metrics.mean_retry_count / baseline_metrics.mean_retry_count
        if baseline_metrics.mean_retry_count > 0
        else 1.0
    )

    report = DegradationReport(
        task_name=task_name,
        mutation_type=mutation_type,
        baseline=baseline_metrics,
        mutated=mutated_metrics,
        success_rate_delta=success_delta,
        runtime_overhead_ratio=runtime_ratio,
        retry_overhead_ratio=retry_ratio,
    )

    log.info(
        "comparison_complete",
        task=task_name,
        mutation=mutation_type,
        baseline_success_rate=round(baseline_metrics.success_rate, 3),
        mutated_success_rate=round(mutated_metrics.success_rate, 3),
        success_delta=round(success_delta, 3),
        runtime_ratio=round(runtime_ratio, 2),
    )

    return report


def compare_all_mutations(
    store: BenchmarkStore,
    task_name: str,
    *,
    agent_name: Optional[str] = None,
    min_runs: int = MIN_RUNS_FOR_COMPARISON,
) -> list[DegradationReport]:
    """Compare baseline against ALL mutation types for a single task.

    Args:
        store: Database access object.
        task_name: Task to analyze.
        agent_name: Optional agent filter.
        min_runs: Minimum runs per condition.

    Returns:
        List of degradation reports, one per mutation type.
        Mutations with insufficient data are skipped (logged as warnings).
    """
    log.info("compare_all_mutations_start", task=task_name)

    mutations = store.get_distinct_mutations()
    reports: list[DegradationReport] = []

    for mutation in mutations:
        try:
            report = compare_task_mutation(
                store, task_name, mutation,
                agent_name=agent_name,
                min_runs=min_runs,
            )
            reports.append(report)
        except InsufficientDataError as exc:
            log.warning(
                "comparison_skipped_insufficient_data",
                task=task_name,
                mutation=mutation,
                reason=str(exc),
            )

    log.info(
        "compare_all_mutations_complete",
        task=task_name,
        reports_generated=len(reports),
        mutations_skipped=len(mutations) - len(reports),
    )

    return reports


def compare_all_tasks(
    store: BenchmarkStore,
    *,
    agent_name: Optional[str] = None,
    min_runs: int = MIN_RUNS_FOR_COMPARISON,
) -> dict[str, list[DegradationReport]]:
    """Compare all tasks against all their mutations.

    Args:
        store: Database access object.
        agent_name: Optional agent filter.
        min_runs: Minimum runs per condition.

    Returns:
        Dictionary mapping task names to their degradation reports.
    """
    log.info("compare_all_tasks_start")

    tasks = store.get_distinct_tasks()
    all_reports: dict[str, list[DegradationReport]] = {}

    for task in tasks:
        reports = compare_all_mutations(
            store, task,
            agent_name=agent_name,
            min_runs=min_runs,
        )
        if reports:
            all_reports[task] = reports

    total_reports = sum(len(r) for r in all_reports.values())
    log.info(
        "compare_all_tasks_complete",
        tasks_analyzed=len(all_reports),
        total_reports=total_reports,
    )

    return all_reports


def format_summary_table(reports: list[DegradationReport]) -> str:
    """Format degradation reports as a readable text table.

    Args:
        reports: List of degradation reports.

    Returns:
        Formatted multi-line string table.
    """
    if not reports:
        return "No degradation reports available."

    header = f"{'Mutation':<25} {'Baseline':>10} {'Mutated':>10} {'Delta':>10} {'Runtime':>10}"
    separator = "-" * len(header)
    lines = [header, separator]

    for r in reports:
        baseline_pct = f"{r.baseline.success_rate * 100:.0f}%"
        mutated_pct = f"{r.mutated.success_rate * 100:.0f}%"
        delta_pct = f"{r.success_rate_delta * 100:+.0f}%"
        runtime = f"{r.runtime_overhead_ratio:.2f}x"

        lines.append(
            f"{r.mutation_type:<25} {baseline_pct:>10} {mutated_pct:>10} "
            f"{delta_pct:>10} {runtime:>10}"
        )

    return "\n".join(lines)
