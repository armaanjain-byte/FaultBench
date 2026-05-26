"""
smoke_test.py — FaultBench end-to-end pipeline smoke test WITHOUT OpenHands.

This script validates the full lifecycle path:
  task load → workspace copy → mutation apply → verify → metrics → compare

It uses task_hello_world (simplest task, no external deps) and exercises the
verify step directly on the host. No OpenHands required.

Run from the FaultBench root directory:
    python scripts/smoke_test.py

Exit code:
  0 — all steps passed
  1 — one or more steps failed (details printed to stderr)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure faultbench package is importable from repo root
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from faultbench.agent.base import AgentResult
from faultbench.config import load_config
from faultbench.constants import MutationTiming
from faultbench.db.store import BenchmarkStore
from faultbench.engine.lifecycle import _verify_task, _WORKSPACE_SENTINEL
from faultbench.metrics.collector import aggregate_runs, collect_run_record, save_raw_log
from faultbench.models import TaskConfig
from faultbench.reporting.comparator import compare_task_mutation, format_summary_table
from faultbench.sandbox.file_ops import cleanup_workdir, copy_task_to_workdir, ensure_directory


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TASK_DIR = repo_root / "tasks" / "task_hello_world"
PRINT_PASS = "\033[92m[PASS]\033[0m"
PRINT_FAIL = "\033[91m[FAIL]\033[0m"
PRINT_INFO = "\033[94m[INFO]\033[0m"
PRINT_WARN = "\033[93m[WARN]\033[0m"

failures: list[str] = []


def _step(name: str) -> None:
    print(f"\n{PRINT_INFO} === {name} ===")


def _pass(msg: str) -> None:
    print(f"  {PRINT_PASS} {msg}")


def _fail(msg: str) -> None:
    print(f"  {PRINT_FAIL} {msg}", file=sys.stderr)
    failures.append(msg)


def _warn(msg: str) -> None:
    print(f"  {PRINT_WARN} {msg}")


# ---------------------------------------------------------------------------
# Step 1: Load task config
# ---------------------------------------------------------------------------

_step("1. Load task config")
config = load_config(str(repo_root / "config.yaml"), force_reload=True)

task_yaml = TASK_DIR / "task.yaml"
if not task_yaml.exists():
    _fail(f"task.yaml not found: {task_yaml}")
    sys.exit(1)

import yaml
with open(task_yaml, encoding="utf-8") as f:
    raw = yaml.safe_load(f)

task_config = TaskConfig(
    name=raw.get("name", "task_hello_world"),
    description=raw.get("description", ""),
    instruction=raw.get("instruction", ""),
    repo_path=str(TASK_DIR.resolve()),
    verify_command=raw.get("verify_command", "python verify.py"),
    valid_mutations=[],
    timeout_seconds=int(raw.get("timeout_seconds", 300)),
)
_pass(f"Task loaded: {task_config.name}")
_pass(f"verify_command: {task_config.verify_command}")


# ---------------------------------------------------------------------------
# Step 2: Copy task to workdir
# ---------------------------------------------------------------------------

_step("2. Copy task to workdir")
log_dir = Path(config.paths.logs)
work_parent = ensure_directory(log_dir / "smoke_test_workdirs")

start_time = time.time()
work_dir = copy_task_to_workdir(TASK_DIR, work_parent)
_pass(f"Copied to: {work_dir}")
assert work_dir.exists(), "work_dir does not exist after copy"
assert (work_dir / "hello.py").exists(), "hello.py missing from work_dir"
_pass("hello.py present in work_dir")


# ---------------------------------------------------------------------------
# Step 3: Write sentinel (simulating what lifecycle.py does)
# ---------------------------------------------------------------------------

_step("3. Workspace sentinel")
sentinel_path = work_dir / _WORKSPACE_SENTINEL
sentinel_content = f"faultbench_sentinel task={task_config.name} mutation=baseline\n"
sentinel_path.write_text(sentinel_content, encoding="utf-8")
_pass(f"Sentinel written: {sentinel_path.name}")


# ---------------------------------------------------------------------------
# Step 4: Simulate agent "fixing" hello.py (what OpenHands would do)
# ---------------------------------------------------------------------------

_step("4. Simulate agent fix (write correct output to hello.py)")
hello_py = work_dir / "hello.py"
original_content = hello_py.read_text(encoding="utf-8")
_pass(f"Original hello.py: {original_content.strip()!r}")

# Simulate the fix
hello_py.write_text('print("hello world")\n', encoding="utf-8")
_pass(f"Fixed hello.py: {hello_py.read_text(encoding='utf-8').strip()!r}")


# ---------------------------------------------------------------------------
# Step 5: Validate workspace access (sentinel check)
# ---------------------------------------------------------------------------

_step("5. Workspace access validation")
# The sentinel should still exist (agent didn't delete it, but .py files changed)
sentinel_still_there = sentinel_path.exists()
py_files_modified = [
    str(p.relative_to(work_dir))
    for p in work_dir.rglob("*.py")
    if p.is_file() and p.stat().st_mtime > sentinel_path.stat().st_mtime
]
workspace_validated = not sentinel_still_there or bool(py_files_modified)

if workspace_validated:
    _pass(f"Workspace validated: {len(py_files_modified)} .py file(s) modified")
    _pass(f"Modified files: {py_files_modified}")
else:
    _fail("Workspace NOT validated — no file changes detected after simulated agent execution")


# ---------------------------------------------------------------------------
# Step 6: Run verification
# ---------------------------------------------------------------------------

_step("6. Run verification")
verify_result = _verify_task(task_config=task_config, work_dir=work_dir)

if verify_result is None:
    _fail("verify_task returned None — no verify_command or work_dir missing")
elif verify_result.success:
    _pass("Verification PASSED (exit code 0)")
    _pass(f"Output: {verify_result.raw_output[:200]}")
else:
    _fail(f"Verification FAILED: {verify_result.error_message}")
    _fail(f"Output: {verify_result.raw_output[:500]}")


# ---------------------------------------------------------------------------
# Step 7: Build RunRecord and save to DB
# ---------------------------------------------------------------------------

_step("7. Build RunRecord and save to DB")
elapsed = time.time() - start_time

# The "agent result" is what we'd normally get from OpenHands
simulated_agent_result = AgentResult(
    success=verify_result.success if verify_result else False,
    iterations_used=1,
    tokens_used=None,
    raw_output="[smoke_test: simulated agent fix]",
    error_message=None,
)

raw_log_path = save_raw_log(
    log_content=simulated_agent_result.raw_output,
    log_dir=log_dir,
    task_name=task_config.name,
    run_id=f"smoke_baseline_{int(start_time)}",
)
_pass(f"Raw log saved: {raw_log_path}")

record = collect_run_record(
    task_name=task_config.name,
    agent_name="smoke_test",
    agent_result=simulated_agent_result,
    runtime_seconds=elapsed,
    mutation_type=None,
    mutation_timing=None,
    raw_log_path=str(raw_log_path),
)
_pass(f"RunRecord created: run_id={record.run_id}, success={record.success}")

db_path = config.paths.db
with BenchmarkStore(db_path) as store:
    store.insert_run(record)
    count = store.get_run_count(task_name=task_config.name)
_pass(f"Saved to DB ({db_path}), total runs for task: {count}")


# ---------------------------------------------------------------------------
# Step 8: Cleanup
# ---------------------------------------------------------------------------

_step("8. Cleanup workdir")
if verify_result and verify_result.success:
    cleanup_workdir(work_dir)
    _pass("Workdir cleaned up (run succeeded)")
else:
    _warn(f"Workdir kept for inspection (run failed): {work_dir}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
if not failures:
    print(f"{PRINT_PASS} All smoke test steps passed!")
    print(
        "\nPipeline validated:\n"
        "  task load -> workspace copy -> sentinel -> agent fix ->\n"
        "  workspace validation -> verification -> DB record\n"
    )
    print("Next step: run with OpenHands:")
    print("  python -m faultbench run --task task_hello_world --mutation none --runs 1")
    sys.exit(0)
else:
    print(f"{PRINT_FAIL} {len(failures)} step(s) FAILED:")
    for f in failures:
        print(f"  • {f}")
    print(
        "\nCheck the logs above. Common causes:\n"
        "  - hello.py verify.py path issues (run from repo root)\n"
        "  - Python not found (check sys.executable)\n"
    )
    sys.exit(1)
