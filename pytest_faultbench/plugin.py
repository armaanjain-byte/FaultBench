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
    if config.getoption("--faultbench"):
        return

    skip = pytest.mark.skip(reason="need --faultbench to run")
    for item in items:
        if "mutate" in item.fixturenames:
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mutate():
    """Provide a context-manager that copies a task dir into a temp workspace."""

    @contextmanager
    def _mutate(task_dir: Path):
        tmp_root = Path(tempfile.mkdtemp())
        work_dir = copy_to_tmp(task_dir, tmp_root)
        try:
            yield work_dir
        finally:
            remove(tmp_root)

    return _mutate
