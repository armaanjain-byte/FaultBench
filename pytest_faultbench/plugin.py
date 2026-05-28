from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from pytest_faultbench.reporting import MutationReport, render_terminal_summary
from pytest_faultbench.workspace import copy_to_tmp, remove


def _faultbench_reports(config: pytest.Config) -> dict[str, MutationReport]:
    reports = getattr(config, "_faultbench_reports", None)
    if reports is None:
        reports = {}
        setattr(config, "_faultbench_reports", reports)
    return reports


def _record_mutation(
    config: pytest.Config, mutation_name: str
) -> None:
    reports = _faultbench_reports(config)
    report = reports.get(mutation_name)
    if report is None:
        reports[mutation_name] = MutationReport(
            mutation_name=mutation_name,
            tests_affected=1,
            failures_detected=False,
            rollback_successful=True,
        )
        return

    report.tests_affected += 1


def _record_rollback(
    config: pytest.Config, mutation_name: str, rollback_successful: bool
) -> None:
    report = _faultbench_reports(config).get(mutation_name)
    if report is not None:
        report.rollback_successful = report.rollback_successful and rollback_successful


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--faultbench",
        action="store_true",
        default=False,
        help="Enable faultbench mutation tests.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "faultbench: mark test as a faultbench mutation test.",
    )
    _faultbench_reports(config)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not config.getoption("--faultbench"):
        skip = pytest.mark.skip(reason="need --faultbench to run")
        for item in items:
            if (
                "mutate" in item.fixturenames
                or "faultbench_workdir" in item.fixturenames
                or item.get_closest_marker("faultbench")
            ):
                item.add_marker(skip)
        return

    # Auto-inject faultbench_workdir for marker-based tests
    for item in items:
        if (
            item.get_closest_marker("faultbench")
            and "faultbench_workdir" not in item.fixturenames
        ):
            item.fixturenames.append("faultbench_workdir")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return

    for mutation_name in getattr(item, "_faultbench_mutations", []):
        mutation_report = _faultbench_reports(item.config).get(mutation_name)
        if mutation_report is not None:
            mutation_report.failures_detected = True


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    if not config.getoption("--faultbench"):
        return

    reports = list(_faultbench_reports(config).values())
    if reports:
        terminalreporter.write_line("")
        terminalreporter.write_line(render_terminal_summary(reports))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mutate(request):
    """Provide a context-manager that copies a task dir into a temp workspace."""

    @contextmanager
    def _mutate(task_dir: Path, *, mutation: str | None = None):
        tmp_root = Path(tempfile.mkdtemp())
        work_dir = copy_to_tmp(task_dir, tmp_root)
        rollback_successful = True

        mut = None
        if mutation == "schema_drift":
            from pytest_faultbench.mutations.schema_drift import SchemaDriftMutation

            mut = SchemaDriftMutation()
            mut.apply(work_dir)
        elif mutation == "config_drift":
            from pytest_faultbench.mutations.config_drift import ConfigDriftMutation

            mut = ConfigDriftMutation()
            mut.apply(work_dir)
        elif mutation == "malformed_config":
            from pytest_faultbench.mutations.malformed_config import (
                MalformedConfigMutation,
            )

            mut = MalformedConfigMutation()
            mut.apply(work_dir)

        if mutation is not None:
            _record_mutation(request.config, mutation)
            mutations = getattr(request.node, "_faultbench_mutations", [])
            mutations.append(mutation)
            setattr(request.node, "_faultbench_mutations", mutations)

        try:
            yield work_dir
        finally:
            try:
                if mut is not None:
                    mut.rollback(work_dir)
            except Exception:
                rollback_successful = False
                raise
            finally:
                if mutation is not None:
                    _record_rollback(request.config, mutation, rollback_successful)
                remove(tmp_root)

    return _mutate


@pytest.fixture
def faultbench_workdir(request, mutate, tmp_path):
    """Isolated workspace with mutation applied, driven by @pytest.mark.faultbench."""
    marker = request.node.get_closest_marker("faultbench")
    mutation_name = marker.kwargs.get("mutation") if marker else None

    try:
        task_dir = request.getfixturevalue("faultbench_task_dir")
    except pytest.FixtureLookupError:
        task_dir = tmp_path / "_faultbench_empty"
        task_dir.mkdir()

    with mutate(task_dir, mutation=mutation_name) as work_dir:
        yield work_dir
