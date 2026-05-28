"""Resilience tests for the mini app.

Run normally:      pytest examples/mini_app/test_app.py
Run with faults:   pytest examples/mini_app/test_app.py --faultbench

The baseline test always passes — the schema is valid.
The faultbench test injects schema drift and proves the app detects it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# Import from the example app (same directory).
import sys
sys.path.insert(0, str(Path(__file__).parent))
from app import validate_schema  # noqa: E402


EXAMPLE_DIR = Path(__file__).parent


# -- Fixture: provide the example project as the task dir -------------------

@pytest.fixture
def faultbench_task_dir(tmp_path: Path) -> Path:
    """Copy the mini_app directory into a temp location for isolation."""
    dest = tmp_path / "mini_app"
    shutil.copytree(EXAMPLE_DIR, dest)
    return dest


# -- Baseline: app works under normal conditions ---------------------------

def test_baseline_schema_valid(tmp_path: Path):
    """The app validates successfully against the original schema."""
    dest = tmp_path / "mini_app"
    shutil.copytree(EXAMPLE_DIR, dest)
    result = validate_schema(dest)
    assert "CREATE TABLE users" in result


# -- Fault injection: schema drift breaks validation -----------------------

@pytest.mark.faultbench(mutation="schema_drift")
def test_schema_drift_detected(faultbench_workdir: Path):
    """After schema_drift mutation, the app correctly rejects the schema.

    This is the core value of faultbench: proving your app fails
    gracefully when its environment changes unexpectedly.
    """
    with pytest.raises(RuntimeError, match="Schema may have drifted"):
        validate_schema(faultbench_workdir)


@pytest.mark.faultbench(mutation="schema_drift")
def test_mutated_schema_content(faultbench_workdir: Path):
    """The mutation renamed 'users' to 'users_v2' in the workspace."""
    schema = (faultbench_workdir / "schema.sql").read_text()
    assert "CREATE TABLE users_v2" in schema
    assert "CREATE TABLE users (" not in schema
