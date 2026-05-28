"""Smoke tests for the FaultBench execution pipeline.

These tests verify that:
1. All package submodules import without errors
2. Configuration defaults are correct
3. All 25 mutation specs (5 tasks × 5 mutation types) load from YAML
4. The mutation registry contains all expected mutation types
5. The CLI entry point is importable and has the expected commands

These are integration smoke tests — they exercise real imports and real
file I/O against the task fixtures, not mocked stubs.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. Import chain
# ---------------------------------------------------------------------------

SUBMODULES = [
    "faultbench",
    "faultbench.cli",
    "faultbench.config",
    "faultbench.constants",
    "faultbench.models",
    "faultbench.logging",
    "faultbench.agent.base",
    "faultbench.agent.openhands_client",
    "faultbench.db.store",
    "faultbench.engine.lifecycle",
    "faultbench.engine.orchestrator",
    "faultbench.metrics.collector",
    "faultbench.metrics.log_parser",
    "faultbench.mutations",
    "faultbench.mutations.base",
    "faultbench.mutations.registry",
    "faultbench.mutations.schema_drift",
    "faultbench.mutations.dependency_drift",
    "faultbench.mutations.config_corruption",
    "faultbench.mutations.missing_file",
    "faultbench.mutations.api_contract_drift",
    "faultbench.reporting.comparator",
    "faultbench.reporting.generator",
    "faultbench.sandbox.file_ops",
]


@pytest.mark.parametrize("module_name", SUBMODULES)
def test_import(module_name: str) -> None:
    """All faultbench submodules import without errors."""
    mod = importlib.import_module(module_name)
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. Configuration defaults
# ---------------------------------------------------------------------------


def test_load_config_returns_defaults(tmp_path, monkeypatch) -> None:
    """load_config() without a config file returns a valid BenchmarkConfig."""
    # Point CWD to a temp directory so no config.yaml is found
    monkeypatch.chdir(tmp_path)

    from archive.faultbench.config import load_config, reset_config_cache
    from archive.faultbench.models import BenchmarkConfig

    reset_config_cache()
    cfg = load_config(force_reload=True)

    assert isinstance(cfg, BenchmarkConfig)
    assert cfg.agent.default == "openhands"
    assert cfg.agent.max_iterations == 30
    assert cfg.benchmark.default_runs == 10
    assert cfg.benchmark.min_runs_for_comparison == 5

    reset_config_cache()


# ---------------------------------------------------------------------------
# 3. Mutation spec loading (all 25 specs)
# ---------------------------------------------------------------------------

TASKS_DIR = Path(__file__).parent.parent.parent / "tasks"

TASK_DIRS = [
    TASKS_DIR / "task_001_todo_api",
    TASKS_DIR / "task_002_csv_pipeline",
    TASKS_DIR / "task_003_user_auth",
    TASKS_DIR / "task_004_markdown_site",
    TASKS_DIR / "task_005_inventory_cli",
]


@pytest.mark.parametrize("task_dir", TASK_DIRS, ids=[d.name for d in TASK_DIRS])
def test_all_mutation_specs_load(task_dir: Path) -> None:
    """All 5 mutation specs load from every task's mutations.yaml."""
    from archive.faultbench.constants import MutationType
    from archive.faultbench.models import MutationSpec
    from archive.faultbench.mutations.registry import get_mutation_spec

    for mt in MutationType:
        spec = get_mutation_spec(task_dir, mt)
        assert isinstance(spec, MutationSpec), f"{task_dir.name}/{mt}: expected MutationSpec"
        assert spec.description, f"{task_dir.name}/{mt}: description is empty"
        assert len(spec.actions) > 0, f"{task_dir.name}/{mt}: no actions"
        assert len(spec.rollback_actions) > 0, f"{task_dir.name}/{mt}: no rollback_actions"


# ---------------------------------------------------------------------------
# 4. Mutation registry completeness
# ---------------------------------------------------------------------------


def test_mutation_registry_covers_all_types() -> None:
    """MUTATION_REGISTRY has an entry for every MutationType."""
    from archive.faultbench.constants import MutationType
    from archive.faultbench.mutations.registry import MUTATION_REGISTRY

    for mt in MutationType:
        assert mt in MUTATION_REGISTRY, f"MutationType.{mt.name} not in MUTATION_REGISTRY"


def test_get_mutation_returns_instance() -> None:
    """get_mutation() returns a concrete BaseMutation instance for each type."""
    from archive.faultbench.constants import MutationType
    from archive.faultbench.mutations.base import BaseMutation
    from archive.faultbench.mutations.registry import get_mutation

    for mt in MutationType:
        instance = get_mutation(mt)
        assert isinstance(instance, BaseMutation)
        assert instance.mutation_type == mt


# ---------------------------------------------------------------------------
# 5. CLI entry point
# ---------------------------------------------------------------------------


def test_cli_main_is_callable() -> None:
    """faultbench.cli.main is a Click group with the expected commands."""
    import click

    from archive.faultbench.cli import main

    assert callable(main)
    assert isinstance(main, click.Group)
    assert "run" in main.commands
    assert "compare" in main.commands
    assert "report" in main.commands


def test_cli_run_help(capsys) -> None:
    """CLI run --help exits cleanly."""
    from click.testing import CliRunner

    from archive.faultbench.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--task" in result.output
    assert "--mutation" in result.output
    assert "--runs" in result.output


def test_cli_mutation_none_maps_to_baseline(monkeypatch, tmp_path) -> None:
    """--mutation none triggers baseline_only=True in run_benchmark."""
    calls: list[dict] = []

    def fake_run_benchmark(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(
        "faultbench.engine.orchestrator.run_benchmark", fake_run_benchmark
    )
    # Also patch the import inside cli
    monkeypatch.setattr(
        "faultbench.cli.run_command.__wrapped__"
        if hasattr(getattr(__import__("faultbench.cli", fromlist=["run_command"]), "run_command"), "__wrapped__")
        else "faultbench.engine.orchestrator.run_benchmark",
        fake_run_benchmark,
        raising=False,
    )

    from click.testing import CliRunner
    from archive.faultbench.cli import main

    runner = CliRunner()
    # We patch run_benchmark via the orchestrator module that cli imports
    import archive.faultbench.engine.orchestrator as orch_mod
    original = orch_mod.run_benchmark
    orch_mod.run_benchmark = fake_run_benchmark
    try:
        result = runner.invoke(main, ["run", "--mutation", "none", "--runs", "1"])
    finally:
        orch_mod.run_benchmark = original

    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0]["baseline_only"] is True
    assert calls[0]["mutation_filter"] is None
