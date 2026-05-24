"""Chart generation for FaultBench benchmark reports.

Produces matplotlib visualizations embedded in HTML reports:
- Success rate bar charts (baseline vs. mutated)
- Runtime comparison charts
- Degradation heatmaps
- Retry/exception distribution plots

All chart functions return the path to the saved PNG file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server/CI use
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from faultbench.logging import get_logger
from faultbench.models import DegradationReport

log = get_logger(__name__)

# Consistent styling
COLORS = {
    "baseline": "#4CAF50",       # Green
    "mutated": "#F44336",        # Red
    "neutral": "#607D8B",        # Blue-grey
    "accent": "#FF9800",         # Orange
    "background": "#FAFAFA",     # Light grey
    "grid": "#E0E0E0",           # Grid lines
}

FONT_CONFIG = {
    "family": "sans-serif",
    "size": 11,
}


def _setup_style() -> None:
    """Apply consistent styling to all charts."""
    plt.rcParams.update({
        "font.family": FONT_CONFIG["family"],
        "font.size": FONT_CONFIG["size"],
        "axes.facecolor": COLORS["background"],
        "figure.facecolor": "white",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.color": COLORS["grid"],
    })


def generate_success_rate_chart(
    reports: list[DegradationReport],
    output_path: Path,
    *,
    title: Optional[str] = None,
) -> Path:
    """Generate a grouped bar chart comparing baseline vs. mutated success rates.

    Args:
        reports: Degradation reports to visualize.
        output_path: Path to save the PNG file.
        title: Optional custom chart title.

    Returns:
        Path to the saved chart image.
    """
    _setup_style()

    if not reports:
        log.warning("chart_skip_empty", chart="success_rate")
        return output_path

    mutations = [r.mutation_type for r in reports]
    baseline_rates = [r.baseline.success_rate * 100 for r in reports]
    mutated_rates = [r.mutated.success_rate * 100 for r in reports]

    fig, ax = plt.subplots(figsize=(10, 6))

    x = range(len(mutations))
    width = 0.35

    bars_baseline = ax.bar(
        [i - width / 2 for i in x], baseline_rates, width,
        label="Baseline", color=COLORS["baseline"], edgecolor="white",
    )
    bars_mutated = ax.bar(
        [i + width / 2 for i in x], mutated_rates, width,
        label="Mutated", color=COLORS["mutated"], edgecolor="white",
    )

    # Add value labels on bars
    for bar in bars_baseline:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2, height + 1,
            f"{height:.0f}%", ha="center", va="bottom", fontsize=9,
        )
    for bar in bars_mutated:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2, height + 1,
            f"{height:.0f}%", ha="center", va="bottom", fontsize=9,
        )

    ax.set_xlabel("Mutation Type")
    ax.set_ylabel("Success Rate (%)")
    ax.set_title(title or "Task Success Rate: Baseline vs. Mutated")
    ax.set_xticks(list(x))
    ax.set_xticklabels(mutations, rotation=30, ha="right")
    ax.set_ylim(0, 110)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(100))
    ax.legend()

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    log.info("chart_generated", chart="success_rate", path=str(output_path))
    return output_path


def generate_runtime_chart(
    reports: list[DegradationReport],
    output_path: Path,
    *,
    title: Optional[str] = None,
) -> Path:
    """Generate a bar chart comparing mean runtime between conditions.

    Args:
        reports: Degradation reports.
        output_path: Path to save the PNG.
        title: Optional custom title.

    Returns:
        Path to the saved chart.
    """
    _setup_style()

    if not reports:
        log.warning("chart_skip_empty", chart="runtime")
        return output_path

    mutations = [r.mutation_type for r in reports]
    baseline_runtimes = [r.baseline.mean_runtime_seconds for r in reports]
    mutated_runtimes = [r.mutated.mean_runtime_seconds for r in reports]

    fig, ax = plt.subplots(figsize=(10, 6))

    x = range(len(mutations))
    width = 0.35

    ax.bar(
        [i - width / 2 for i in x], baseline_runtimes, width,
        label="Baseline", color=COLORS["baseline"], edgecolor="white",
    )
    ax.bar(
        [i + width / 2 for i in x], mutated_runtimes, width,
        label="Mutated", color=COLORS["mutated"], edgecolor="white",
    )

    ax.set_xlabel("Mutation Type")
    ax.set_ylabel("Mean Runtime (seconds)")
    ax.set_title(title or "Mean Runtime: Baseline vs. Mutated")
    ax.set_xticks(list(x))
    ax.set_xticklabels(mutations, rotation=30, ha="right")
    ax.legend()

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    log.info("chart_generated", chart="runtime", path=str(output_path))
    return output_path


def generate_degradation_heatmap(
    task_reports: dict[str, list[DegradationReport]],
    output_path: Path,
    *,
    title: Optional[str] = None,
) -> Path:
    """Generate a heatmap showing degradation across tasks and mutations.

    Rows are tasks, columns are mutation types, cells are success rate
    delta (red = worse, green = no degradation).

    Args:
        task_reports: Mapping of task name to its degradation reports.
        output_path: Path to save the PNG.
        title: Optional custom title.

    Returns:
        Path to the saved chart.
    """
    _setup_style()

    if not task_reports:
        log.warning("chart_skip_empty", chart="heatmap")
        return output_path

    # Collect all unique mutation types across tasks
    all_mutations: list[str] = []
    for reports in task_reports.values():
        for r in reports:
            if r.mutation_type not in all_mutations:
                all_mutations.append(r.mutation_type)

    tasks = list(task_reports.keys())

    # Build the data matrix
    data: list[list[float]] = []
    for task in tasks:
        row: list[float] = []
        reports_by_mutation = {
            r.mutation_type: r for r in task_reports[task]
        }
        for mutation in all_mutations:
            if mutation in reports_by_mutation:
                delta = reports_by_mutation[mutation].success_rate_delta * 100
                row.append(delta)
            else:
                row.append(0.0)  # No data
        data.append(row)

    fig, ax = plt.subplots(figsize=(max(8, len(all_mutations) * 2), max(4, len(tasks) * 1.2)))

    # Create heatmap
    cmap = plt.cm.RdYlGn  # Red (bad) to Green (good)
    im = ax.imshow(data, cmap=cmap, aspect="auto", vmin=-100, vmax=10)

    # Labels
    ax.set_xticks(range(len(all_mutations)))
    ax.set_xticklabels(all_mutations, rotation=45, ha="right")
    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels(tasks)
    ax.set_title(title or "Success Rate Degradation Heatmap (%)")

    # Add text annotations in cells
    for i in range(len(tasks)):
        for j in range(len(all_mutations)):
            value = data[i][j]
            color = "white" if abs(value) > 40 else "black"
            ax.text(j, i, f"{value:+.0f}%", ha="center", va="center",
                    color=color, fontsize=10, fontweight="bold")

    fig.colorbar(im, ax=ax, label="Success Rate Delta (%)")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    log.info("chart_generated", chart="heatmap", path=str(output_path))
    return output_path


def generate_retry_distribution_chart(
    reports: list[DegradationReport],
    output_path: Path,
    *,
    title: Optional[str] = None,
) -> Path:
    """Generate a chart comparing retry counts between conditions.

    Args:
        reports: Degradation reports.
        output_path: Path to save the PNG.
        title: Optional custom title.

    Returns:
        Path to the saved chart.
    """
    _setup_style()

    if not reports:
        log.warning("chart_skip_empty", chart="retry_distribution")
        return output_path

    mutations = [r.mutation_type for r in reports]
    baseline_retries = [r.baseline.mean_retry_count for r in reports]
    mutated_retries = [r.mutated.mean_retry_count for r in reports]

    fig, ax = plt.subplots(figsize=(10, 6))

    x = range(len(mutations))
    width = 0.35

    ax.bar(
        [i - width / 2 for i in x], baseline_retries, width,
        label="Baseline", color=COLORS["baseline"], edgecolor="white",
    )
    ax.bar(
        [i + width / 2 for i in x], mutated_retries, width,
        label="Mutated", color=COLORS["accent"], edgecolor="white",
    )

    ax.set_xlabel("Mutation Type")
    ax.set_ylabel("Mean Retry Count")
    ax.set_title(title or "Agent Retry Behavior: Baseline vs. Mutated")
    ax.set_xticks(list(x))
    ax.set_xticklabels(mutations, rotation=30, ha="right")
    ax.legend()

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    log.info("chart_generated", chart="retry_distribution", path=str(output_path))
    return output_path
