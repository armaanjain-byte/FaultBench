from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from pytest_faultbench.workspace import copy_to_tmp, remove


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mutate():
    """Provide a context-manager that copies a task dir into a temp workspace."""

    @contextmanager
    def _mutate(task_dir: Path, *, mutation: str | None = None):
        tmp_root = Path(tempfile.mkdtemp())
        work_dir = copy_to_tmp(task_dir, tmp_root)

        mut = None
        if mutation == "schema_drift":
            from pytest_faultbench.mutations.schema_drift import SchemaDriftMutation

            mut = SchemaDriftMutation()
            mut.apply(work_dir)

        try:
            yield work_dir
        finally:
            if mut is not None:
                mut.rollback(work_dir)
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
