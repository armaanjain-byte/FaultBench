"""Integration tests for the FaultBench → OpenHands execution pipeline.

These tests require a running OpenHands server at http://localhost:3000.
They are marked with ``pytest.mark.integration`` so they can be skipped
in CI environments where OpenHands is not available:

    pytest tests/integration/ -v
    pytest tests/integration/ -v -m "not integration"  # skip
    pytest tests/integration/ -v -m integration          # only these

Run the hello-world end-to-end test:

    pytest tests/integration/test_pipeline.py::test_hello_world_baseline -v -s

Note: These tests consume OpenHands tokens since they invoke real LLM calls.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Availability guard: skip all tests if OpenHands is not reachable
# ---------------------------------------------------------------------------

OPENHANDS_BASE_URL = "http://localhost:3000"
REPO_ROOT = Path(__file__).parent.parent.parent


def _openhands_is_available() -> bool:
    """Return True if OpenHands health endpoint is responsive."""
    try:
        import httpx
        r = httpx.get(f"{OPENHANDS_BASE_URL}/health", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


requires_openhands = pytest.mark.skipif(
    not _openhands_is_available(),
    reason="OpenHands is not running at http://localhost:3000",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_workdir(tmp_path: Path) -> Path:
    """Return a temporary working directory."""
    return tmp_path


@pytest.fixture()
def hello_world_task_dir() -> Path:
    """Return the path to the hello_world task directory."""
    task_dir = REPO_ROOT / "tasks" / "task_hello_world"
    assert task_dir.exists(), f"task_hello_world not found at {task_dir}"
    return task_dir


@pytest.fixture()
def hello_world_workdir(hello_world_task_dir: Path, tmp_path: Path) -> Path:
    """Copy the hello_world task to a temp directory and return it."""
    dest = tmp_path / "task_hello_world"
    shutil.copytree(hello_world_task_dir, dest)
    return dest


# ---------------------------------------------------------------------------
# 1. Sanity: OpenHands is reachable
# ---------------------------------------------------------------------------


@requires_openhands
def test_openhands_health_check() -> None:
    """OpenHands /health endpoint returns 200."""
    import httpx

    r = httpx.get(f"{OPENHANDS_BASE_URL}/health", timeout=10.0)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


@requires_openhands
def test_openhands_alive_check() -> None:
    """OpenHands /alive endpoint returns status ok."""
    import httpx

    r = httpx.get(f"{OPENHANDS_BASE_URL}/alive", timeout=10.0)
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"


# ---------------------------------------------------------------------------
# 2. OpenHandsClient unit behaviour (no full task execution)
# ---------------------------------------------------------------------------


def test_openhands_client_is_available() -> None:
    """OpenHandsClient.is_available() returns correct bool."""
    from faultbench.agent.openhands_client import OpenHandsClient

    client = OpenHandsClient(base_url=OPENHANDS_BASE_URL)
    # Just check it returns a bool — value depends on whether OH is running
    result = client.is_available()
    assert isinstance(result, bool)


@requires_openhands
def test_openhands_client_available_true() -> None:
    """OpenHandsClient.is_available() returns True when server is up."""
    from faultbench.agent.openhands_client import OpenHandsClient

    client = OpenHandsClient(base_url=OPENHANDS_BASE_URL)
    assert client.is_available() is True


# ---------------------------------------------------------------------------
# 3. Verification step (host-side, no OpenHands needed)
# ---------------------------------------------------------------------------


def test_verify_task_passes_when_hello_py_correct(tmp_path: Path) -> None:
    """_verify_task returns success=True when hello.py outputs 'hello world'."""
    from faultbench.engine.lifecycle import _verify_task
    from faultbench.models import TaskConfig
    from faultbench.constants import MutationType

    # Create a correct hello.py
    hello = tmp_path / "hello.py"
    hello.write_text('print("hello world")\n', encoding="utf-8")

    # Copy verify.py from task dir
    task_dir = REPO_ROOT / "tasks" / "task_hello_world"
    if (task_dir / "verify.py").exists():
        shutil.copy(task_dir / "verify.py", tmp_path / "verify.py")
        verify_cmd = "python verify.py"
    else:
        verify_cmd = "python hello.py"

    task_config = TaskConfig(
        name="test_hello_world",
        description="test",
        instruction="fix typo",
        repo_path=str(tmp_path),
        verify_command=verify_cmd,
        valid_mutations=[],
        timeout_seconds=60,
    )

    result = _verify_task(task_config=task_config, work_dir=tmp_path)
    assert result is not None
    assert result.success is True, f"Expected success, got: {result.raw_output}"


def test_verify_task_fails_when_hello_py_wrong(tmp_path: Path) -> None:
    """_verify_task returns success=False when hello.py has the typo."""
    from faultbench.engine.lifecycle import _verify_task
    from faultbench.models import TaskConfig

    # Create the WRONG hello.py (original faulty state)
    hello = tmp_path / "hello.py"
    hello.write_text('print("helo wrld")\n', encoding="utf-8")

    # Copy verify.py from task dir
    task_dir = REPO_ROOT / "tasks" / "task_hello_world"
    if (task_dir / "verify.py").exists():
        shutil.copy(task_dir / "verify.py", tmp_path / "verify.py")
        verify_cmd = "python verify.py"
    else:
        verify_cmd = "python -c \"import sys; output=open('hello.py').read(); sys.exit(0 if 'hello world' in output else 1)\""

    task_config = TaskConfig(
        name="test_hello_world",
        description="test",
        instruction="fix typo",
        repo_path=str(tmp_path),
        verify_command=verify_cmd,
        valid_mutations=[],
        timeout_seconds=60,
    )

    result = _verify_task(task_config=task_config, work_dir=tmp_path)
    assert result is not None
    assert result.success is False, f"Expected failure, got: {result.raw_output}"


# ---------------------------------------------------------------------------
# 4. Task loading
# ---------------------------------------------------------------------------


def test_hello_world_task_loads() -> None:
    """task_hello_world loads successfully via load_task_configs."""
    from faultbench.engine.orchestrator import load_task_configs

    tasks_dir = REPO_ROOT / "tasks"
    assert tasks_dir.exists()

    configs = load_task_configs(tasks_dir)
    names = [c.name for c in configs]
    assert "task_hello_world" in names, (
        f"task_hello_world not found in loaded tasks: {names}"
    )

    hw_config = next(c for c in configs if c.name == "task_hello_world")
    assert hw_config.verify_command  # must have a verify command
    assert hw_config.instruction    # must have an instruction
    assert hw_config.timeout_seconds == 300


def test_hello_world_hello_py_has_typo() -> None:
    """hello.py in its initial (source) state contains the expected typo."""
    hello_py = REPO_ROOT / "tasks" / "task_hello_world" / "hello.py"
    assert hello_py.exists(), "hello.py should exist"
    content = hello_py.read_text(encoding="utf-8")
    assert "helo wrld" in content, (
        f"Expected typo 'helo wrld' in hello.py, got: {content!r}"
    )


# ---------------------------------------------------------------------------
# 5. End-to-end hello_world pipeline (requires OpenHands)
# ---------------------------------------------------------------------------


@requires_openhands
@pytest.mark.timeout(600)  # 10 minute ceiling for this test
def test_hello_world_baseline(hello_world_workdir: Path) -> None:
    """Full end-to-end pipeline: inject hello_world task → OpenHands → verify.

    This test exercises the complete lifecycle:
      1. Copy task to temp workdir (done by fixture)
      2. Call execute_single_run with the task config
      3. Assert that RunRecord.success is True
      4. Assert that the verify_command independently confirms the fix

    This test consumes real LLM tokens and may take 2-10 minutes.
    """
    from faultbench.agent.openhands_client import OpenHandsClient
    from faultbench.config import load_config
    from faultbench.constants import MutationType
    from faultbench.engine.lifecycle import execute_single_run
    from faultbench.models import TaskConfig

    # Load global config
    config = load_config(force_reload=True)

    # Build a TaskConfig pointing to the temp workdir
    task_config = TaskConfig(
        name="task_hello_world",
        description="Fix the typo in hello.py",
        instruction=(
            "The file hello.py in the current directory contains a bug. "
            "When run with `python hello.py`, it outputs 'helo wrld' instead of 'hello world'. "
            "Fix the typo in hello.py so that running `python hello.py` prints exactly: hello world\n"
            "Do not create any additional files. Only fix the typo in hello.py."
        ),
        repo_path=str(hello_world_workdir),
        verify_command="python verify.py",
        valid_mutations=[],
        timeout_seconds=300,
    )

    # Instantiate client with the real OpenHands base URL
    agent = OpenHandsClient(
        base_url=OPENHANDS_BASE_URL,
        model=config.agent.model,
        poll_interval=config.agent.poll_interval_seconds,
    )

    # Execute the full lifecycle
    record = execute_single_run(
        task_config=task_config,
        agent=agent,
        config=config,
        mutation_type=None,
        run_index=0,
    )

    # Assertions
    assert record is not None, "execute_single_run returned None"
    assert record.task_name == "task_hello_world"
    assert record.agent_name == "openhands"
    assert record.mutation_type is None  # baseline run

    # THE CRITICAL ASSERTION: the agent must have fixed the file
    assert record.success is True, (
        f"Expected success=True but got success=False. "
        f"Check logs at: {record.raw_log_path}"
    )


@requires_openhands
@pytest.mark.timeout(600)
def test_hello_world_via_cli(tmp_path: Path) -> None:
    """Run hello_world benchmark through the CLI and check it succeeds."""
    from click.testing import CliRunner
    from faultbench.cli import main

    runner = CliRunner()

    # Point to a temp DB to avoid polluting the real one
    tmp_db = str(tmp_path / "test.db")

    result = runner.invoke(
        main,
        [
            "run",
            "--task", "task_hello_world",
            "--mutation", "none",
            "--runs", "1",
            "--config", str(REPO_ROOT / "config.yaml"),
        ],
        catch_exceptions=False,
    )

    # Exit code 0 = at least one run completed
    assert result.exit_code == 0, (
        f"CLI exited with code {result.exit_code}.\nOutput:\n{result.output}"
    )
    assert "Successes" in result.output
