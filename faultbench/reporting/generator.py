"""HTML report generation for FaultBench.

Orchestrates the full report pipeline:
1. Fetch run data from the database
2. Compute degradation comparisons
3. Generate matplotlib charts
4. Render Jinja2 HTML template
5. Save the final report

This module ties together comparator, charts, and the Jinja2 template.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

import jinja2

import faultbench
from faultbench.db.store import BenchmarkStore
from faultbench.logging import get_logger
from faultbench.models import DegradationReport
from faultbench.reporting.charts import (
    generate_degradation_heatmap,
    generate_retry_distribution_chart,
    generate_runtime_chart,
    generate_success_rate_chart,
)
from faultbench.reporting.comparator import compare_all_tasks

log = get_logger(__name__)


def generate_report(
    store: BenchmarkStore,
    output_dir: Path,
    *,
    agent_name: Optional[str] = None,
    min_runs: int = 5,
    report_title: str = "FaultBench Benchmark Report",
) -> Path:
    """Generate a complete HTML benchmark report.

    Args:
        store: Database with run records.
        output_dir: Directory to write the report and charts.
        agent_name: Optional agent name filter.
        min_runs: Minimum runs per condition for comparisons.
        report_title: Title shown in the report header.

    Returns:
        Path to the generated HTML report file.

    Raises:
        RuntimeError: If no data is available to report on.
    """
    log.info("report_generation_start", output_dir=str(output_dir), agent=agent_name)

    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Run comparisons
    task_reports = compare_all_tasks(
        store, agent_name=agent_name, min_runs=min_runs
    )

    if not task_reports:
        log.warning("report_no_data", action="generating_empty_report")

    # Flatten all reports for the summary table
    all_reports: list[DegradationReport] = []
    for reports in task_reports.values():
        all_reports.extend(reports)

    # Step 2: Generate charts
    chart_paths = _generate_all_charts(all_reports, task_reports, charts_dir)

    # Step 3: Compute summary statistics
    summary = _compute_summary(all_reports, store)

    # Step 4: Render HTML
    html_content = _render_template(
        report_title=report_title,
        agent_name=agent_name or "all agents",
        all_reports=all_reports,
        task_reports=task_reports,
        chart_paths=chart_paths,
        summary=summary,
    )

    # Step 5: Save
    report_path = output_dir / "report.html"
    report_path.write_text(html_content, encoding="utf-8")

    log.info(
        "report_generation_complete",
        path=str(report_path),
        tasks=len(task_reports),
        comparisons=len(all_reports),
    )

    return report_path


def _generate_all_charts(
    all_reports: list[DegradationReport],
    task_reports: dict[str, list[DegradationReport]],
    charts_dir: Path,
) -> dict[str, str]:
    """Generate all chart images and return relative paths.

    Args:
        all_reports: Flat list of all degradation reports.
        task_reports: Reports grouped by task.
        charts_dir: Directory for chart images.

    Returns:
        Dictionary mapping chart name to relative file path.
    """
    chart_paths: dict[str, str] = {}

    if not all_reports:
        return chart_paths

    try:
        success_path = generate_success_rate_chart(
            all_reports, charts_dir / "success_rate.png"
        )
        chart_paths["success_rate"] = f"charts/{success_path.name}"
    except Exception as exc:
        log.error("chart_generation_failed", chart="success_rate", error=str(exc))

    try:
        runtime_path = generate_runtime_chart(
            all_reports, charts_dir / "runtime.png"
        )
        chart_paths["runtime"] = f"charts/{runtime_path.name}"
    except Exception as exc:
        log.error("chart_generation_failed", chart="runtime", error=str(exc))

    try:
        heatmap_path = generate_degradation_heatmap(
            task_reports, charts_dir / "heatmap.png"
        )
        chart_paths["heatmap"] = f"charts/{heatmap_path.name}"
    except Exception as exc:
        log.error("chart_generation_failed", chart="heatmap", error=str(exc))

    try:
        retries_path = generate_retry_distribution_chart(
            all_reports, charts_dir / "retries.png"
        )
        chart_paths["retries"] = f"charts/{retries_path.name}"
    except Exception as exc:
        log.error("chart_generation_failed", chart="retries", error=str(exc))

    return chart_paths


def _compute_summary(
    all_reports: list[DegradationReport],
    store: BenchmarkStore,
) -> dict[str, str | int | float]:
    """Compute executive summary statistics.

    Args:
        all_reports: All degradation reports.
        store: Database for total run count.

    Returns:
        Dictionary of summary values for the template.
    """
    total_runs = store.get_run_count()
    tasks = store.get_distinct_tasks()
    mutations = store.get_distinct_mutations()

    if all_reports:
        baseline_rates = [r.baseline.success_rate * 100 for r in all_reports]
        mutated_rates = [r.mutated.success_rate * 100 for r in all_reports]
        deltas = [r.success_rate_delta * 100 for r in all_reports]
        runtime_ratios = [r.runtime_overhead_ratio for r in all_reports]

        mean_baseline = sum(baseline_rates) / len(baseline_rates)
        mean_mutated = sum(mutated_rates) / len(mutated_rates)
        worst_delta = min(deltas)
        avg_runtime = sum(runtime_ratios) / len(runtime_ratios)
    else:
        mean_baseline = 0.0
        mean_mutated = 0.0
        worst_delta = 0.0
        avg_runtime = 1.0

    return {
        "total_runs": total_runs,
        "tasks_analyzed": len(tasks),
        "mutations_tested": len(mutations),
        "mean_baseline_success": f"{mean_baseline:.0f}",
        "mean_mutated_success": f"{mean_mutated:.0f}",
        "worst_degradation": f"{worst_delta:+.0f}",
        "avg_runtime_overhead": f"{avg_runtime:.2f}",
    }


def _render_template(
    *,
    report_title: str,
    agent_name: str,
    all_reports: list[DegradationReport],
    task_reports: dict[str, list[DegradationReport]],
    chart_paths: dict[str, str],
    summary: dict[str, str | int | float],
) -> str:
    """Render the Jinja2 HTML template with report data.

    Args:
        report_title: Report title string.
        agent_name: Agent name label.
        all_reports: All degradation reports (for summary table).
        task_reports: Reports grouped by task (for detail sections).
        chart_paths: Relative paths to chart images.
        summary: Executive summary statistics.

    Returns:
        Rendered HTML string.
    """
    template_dir = Path(__file__).parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=jinja2.select_autoescape(["html"]),
    )

    template = env.get_template("report.html.j2")

    rendered = template.render(
        report_title=report_title,
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        version=faultbench.__version__,
        agent_name=agent_name,
        total_runs=summary["total_runs"],
        tasks_analyzed=summary["tasks_analyzed"],
        mutations_tested=summary["mutations_tested"],
        mean_baseline_success=summary["mean_baseline_success"],
        mean_mutated_success=summary["mean_mutated_success"],
        worst_degradation=summary["worst_degradation"],
        avg_runtime_overhead=summary["avg_runtime_overhead"],
        all_reports=all_reports,
        task_reports=task_reports,
        chart_paths=chart_paths,
    )

    log.info("template_rendered", template="report.html.j2")
    return rendered
