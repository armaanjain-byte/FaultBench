"""Command-line interface for FaultBench.

Entry point for all benchmark operations:

* ``faultbench run``     — execute one or more benchmark runs
* ``faultbench compare`` — compare baseline vs. mutated run statistics
* ``faultbench report``  — generate an HTML report from stored runs

Usage examples::

    # Baseline-only run (no mutations applied)
    faultbench run --task task_001_todo_api --mutation none --runs 1

    # Run with a specific mutation
    faultbench run --task task_001_todo_api --mutation schema_drift --runs 3

    # Run all mutations for a task
    faultbench run --task task_001_todo_api --runs 5

    # Compare results
    faultbench compare --task task_001_todo_api --mutation schema_drift

    # Generate HTML report
    faultbench report --output reports/
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from faultbench.logging import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _resolve_mutation_args(
    mutation: str,
) -> tuple[Optional[str], bool, bool]:
    """Translate the ``--mutation`` flag into orchestrator arguments.

    Args:
        mutation: Value of the ``--mutation`` option.

    Returns:
        Tuple of ``(mutation_filter, baseline_only, mutations_only)``.

    Rules:
    * ``"none"``  → no mutation filter, baseline-only mode
    * ``"all"``   → no filter, run everything (baseline + all mutations)
    * any string  → pass as ``mutation_filter``, not baseline-only
    """
    mutation_lower = mutation.strip().lower()

    if mutation_lower == "none":
        return None, True, False
    if mutation_lower == "all":
        return None, False, False
    return mutation, False, False


# --------------------------------------------------------------------------- #
# CLI group                                                                   #
# --------------------------------------------------------------------------- #


@click.group()
@click.version_option(package_name="faultbench", prog_name="faultbench")
def main() -> None:
    """FaultBench — stress-test coding agents under adversarial runtime conditions.

    Run benchmarks, compare results, and generate reports from the
    stored run database.
    """


# --------------------------------------------------------------------------- #
# run command                                                                 #
# --------------------------------------------------------------------------- #


@main.command("run")
@click.option(
    "--task",
    "-t",
    default=None,
    metavar="TASK_NAME",
    help=(
        "Run only the task matching this name substring.  "
        "Omit to run all tasks."
    ),
)
@click.option(
    "--mutation",
    "-m",
    default="none",
    show_default=True,
    metavar="MUTATION",
    help=(
        "Mutation type to apply: schema_drift, dependency_drift, "
        "config_corruption, missing_file, api_contract_drift, "
        "'none' (baseline only), or 'all'."
    ),
)
@click.option(
    "--runs",
    "-n",
    default=None,
    type=int,
    metavar="N",
    help="Number of runs per condition (overrides config default).",
)
@click.option(
    "--baseline-only",
    is_flag=True,
    default=False,
    help="Skip all mutation runs; execute only clean baseline runs.",
)
@click.option(
    "--mutations-only",
    is_flag=True,
    default=False,
    help="Skip baseline runs; execute only mutation runs.",
)
@click.option(
    "--config",
    "-c",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to config.yaml (defaults to ./config.yaml).",
)
def run_command(
    task: Optional[str],
    mutation: str,
    runs: Optional[int],
    baseline_only: bool,
    mutations_only: bool,
    config: Optional[str],
) -> None:
    """Execute one or more benchmark runs.

    Examples:

    \b
      # Baseline run — no mutation applied
      faultbench run --task task_001_todo_api --mutation none --runs 1

    \b
      # Schema-drift mutation, 3 runs
      faultbench run --task task_001_todo_api --mutation schema_drift --runs 3

    \b
      # All mutations, 5 runs each
      faultbench run --task task_001_todo_api --mutation all --runs 5
    """
    from faultbench.engine.orchestrator import run_benchmark

    # --baseline-only / --mutations-only flags take precedence over --mutation
    if baseline_only or mutations_only:
        mutation_filter: Optional[str] = None
        _baseline_only = baseline_only
        _mutations_only = mutations_only
    else:
        mutation_filter, _baseline_only, _mutations_only = _resolve_mutation_args(mutation)

    click.echo(
        click.style("FaultBench", fg="cyan", bold=True)
        + " run starting"
        + (f" [task={task}]" if task else " [all tasks]")
        + (f" [mutation={mutation}]")
        + (f" [runs={runs}]" if runs else "")
    )

    try:
        records = run_benchmark(
            config_path=config,
            task_filter=task,
            mutation_filter=mutation_filter,
            num_runs=runs,
            baseline_only=_baseline_only,
            mutations_only=_mutations_only,
        )
    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(
            click.style("ERROR: ", fg="red", bold=True) + str(exc),
            err=True,
        )
        log.exception("cli_run_failed", error=str(exc))
        sys.exit(1)

    # Summary
    total = len(records)
    successes = sum(1 for r in records if r.success)
    failures = total - successes

    click.echo()
    click.echo(click.style("Run complete", fg="green", bold=True))
    click.echo(f"  Total runs : {total}")
    click.echo(f"  Successes  : {click.style(str(successes), fg='green')}")
    click.echo(f"  Failures   : {click.style(str(failures), fg='red' if failures else 'white')}")

    if total == 0:
        click.echo(
            click.style(
                "\nNo tasks matched the filter — nothing was run.",
                fg="yellow",
            )
        )

    sys.exit(0)


# --------------------------------------------------------------------------- #
# compare command                                                             #
# --------------------------------------------------------------------------- #


@main.command("compare")
@click.option(
    "--task",
    "-t",
    required=True,
    metavar="TASK_NAME",
    help="Task name to compare.",
)
@click.option(
    "--mutation",
    "-m",
    required=True,
    metavar="MUTATION",
    help="Mutation type to compare against baseline (e.g., schema_drift).",
)
@click.option(
    "--agent",
    default=None,
    metavar="AGENT_NAME",
    help="Filter runs by agent name.",
)
@click.option(
    "--db",
    default=None,
    type=click.Path(),
    help="Path to the SQLite database (defaults to config value).",
)
@click.option(
    "--min-runs",
    default=None,
    type=int,
    metavar="N",
    help="Minimum runs required per condition (defaults to config value).",
)
def compare_command(
    task: str,
    mutation: str,
    agent: Optional[str],
    db: Optional[str],
    min_runs: Optional[int],
) -> None:
    """Compare baseline vs. mutated runs for a task.

    Prints a degradation table showing success-rate delta, runtime
    overhead, and retry overhead.

    Requires at least --min-runs recorded runs per condition.
    """
    from faultbench.config import load_config
    from faultbench.db.store import BenchmarkStore
    from faultbench.reporting.comparator import (
        InsufficientDataError,
        compare_task_mutation,
        format_summary_table,
    )

    config = load_config()
    db_path = db or config.paths.db
    effective_min_runs = min_runs or config.benchmark.min_runs_for_comparison

    try:
        with BenchmarkStore(db_path) as store:
            report = compare_task_mutation(
                store,
                task,
                mutation,
                agent_name=agent,
                min_runs=effective_min_runs,
            )
        click.echo(format_summary_table([report]))
    except InsufficientDataError as exc:
        click.echo(
            click.style("Insufficient data: ", fg="yellow", bold=True) + str(exc),
            err=True,
        )
        sys.exit(1)
    except Exception as exc:
        click.echo(
            click.style("ERROR: ", fg="red", bold=True) + str(exc),
            err=True,
        )
        sys.exit(1)


# --------------------------------------------------------------------------- #
# report command                                                              #
# --------------------------------------------------------------------------- #


@main.command("report")
@click.option(
    "--output",
    "-o",
    default="reports/",
    show_default=True,
    type=click.Path(),
    help="Directory to write the HTML report and chart images.",
)
@click.option(
    "--agent",
    default=None,
    metavar="AGENT_NAME",
    help="Filter runs by agent name.",
)
@click.option(
    "--db",
    default=None,
    type=click.Path(),
    help="Path to the SQLite database (defaults to config value).",
)
@click.option(
    "--min-runs",
    default=None,
    type=int,
    metavar="N",
    help="Minimum runs required per condition for a comparison to appear.",
)
@click.option(
    "--title",
    default="FaultBench Benchmark Report",
    show_default=True,
    help="Title shown in the report header.",
)
def report_command(
    output: str,
    agent: Optional[str],
    db: Optional[str],
    min_runs: Optional[int],
    title: str,
) -> None:
    """Generate an HTML benchmark report.

    Reads persisted run records from the database, computes degradation
    comparisons, and produces a self-contained HTML report with charts.
    """
    from faultbench.config import load_config
    from faultbench.db.store import BenchmarkStore
    from faultbench.reporting.generator import generate_report

    config = load_config()
    db_path = db or config.paths.db
    output_dir = Path(output)
    effective_min_runs = min_runs or config.benchmark.min_runs_for_comparison

    try:
        with BenchmarkStore(db_path) as store:
            report_path = generate_report(
                store,
                output_dir,
                agent_name=agent,
                min_runs=effective_min_runs,
                report_title=title,
            )
        click.echo(
            click.style("Report generated: ", fg="green")
            + str(report_path)
        )
    except Exception as exc:
        click.echo(
            click.style("ERROR: ", fg="red", bold=True) + str(exc),
            err=True,
        )
        sys.exit(1)
