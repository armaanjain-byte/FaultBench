"""Single-run lifecycle manager for FaultBench.

Manages the full lifecycle of ONE benchmark run:

1. Prepare working directory (copy task repo)
2. Apply mutation (if any)
3. Launch the coding agent
4. Collect execution metrics
5. Parse logs
6. Build RunRecord
7. Save raw logs
8. Rollback mutation
9. Cleanup working directory

This module is called by the orchestrator for each individual run.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from faultbench.agent.base import AgentExecutionError, AgentResult, BaseAgent
from faultbench.constants import MutationTiming, MutationType
from faultbench.logging import get_logger
from faultbench.metrics.collector import collect_run_record, save_raw_log
from faultbench.models import BenchmarkConfig, MutationSpec, RunRecord, TaskConfig
from faultbench.mutations.registry import get_mutation, get_mutation_spec
from faultbench.sandbox.file_ops import cleanup_workdir, copy_task_to_workdir, ensure_directory

# Name of the sentinel file written into work_dir before agent execution.
# If OpenHands deletes or modifies this file, we know it can see the workdir.
_WORKSPACE_SENTINEL = ".faultbench_sentinel"

log = get_logger(__name__)


class LifecycleError(Exception):
    """Raised when a lifecycle step fails irrecoverably."""


def execute_single_run(
    *,
    task_config: TaskConfig,
    agent: BaseAgent,
    config: BenchmarkConfig,
    mutation_type: Optional[MutationType] = None,
    run_index: int = 0,
) -> RunRecord:
    """Execute a single benchmark run through the full lifecycle.

    Args:
        task_config: Configuration for the benchmark task.
        agent: The coding agent to execute the task.
        config: Global benchmark configuration.
        mutation_type: If set, apply this mutation before execution.
            ``None`` means a clean baseline run.
        run_index: Index of this run within a batch (for logging).

    Returns:
        A fully populated :class:`RunRecord` with metrics.
    """
    mutation_label = str(mutation_type) if mutation_type else "baseline"
    log.info(
        "lifecycle_start",
        task=task_config.name,
        mutation=mutation_label,
        run_index=run_index,
        agent=agent.agent_name,
    )

    start_time = time.time()
    task_dir = Path(task_config.repo_path)
    log_dir = Path(config.paths.logs)
    
    work_parent = ensure_directory(Path("logs/workdirs"))

    work_dir: Optional[Path] = None
    mutation_spec: Optional[MutationSpec] = None
    mutation_applied = False

    try:
        # Step 1: Copy task to working directory
        work_dir = copy_task_to_workdir(task_dir, work_parent)
        log.info("lifecycle_task_copied", work_dir=str(work_dir))

        # Step 2: Apply mutation (if requested)
        if mutation_type is not None:
            mutation_spec = _load_and_apply_mutation(work_dir, mutation_type)
            mutation_applied = True

        # Step 2b: Write workspace sentinel for access validation.
        # OpenHands must be able to see/modify this file for the benchmark
        # to have any scientific validity.  We check it after execution.
        sentinel_path = work_dir / _WORKSPACE_SENTINEL
        sentinel_content = f"faultbench_sentinel task={task_config.name} mutation={mutation_label}\n"
        sentinel_path.write_text(sentinel_content, encoding="utf-8")
        log.info(
            "lifecycle_sentinel_written",
            path=str(sentinel_path),
            work_dir=str(work_dir),
        )

        # Step 3: Execute the agent
        agent_result = _execute_agent(
            agent=agent,
            instruction=task_config.instruction,
            workspace_dir=str(work_dir),
            max_iterations=config.agent.max_iterations,
            timeout_seconds=task_config.timeout_seconds,
        )

        elapsed = time.time() - start_time

        # Step 3b: Validate that OpenHands actually operated on work_dir.
        _validate_workspace_access(
            work_dir=work_dir,
            sentinel_path=sentinel_path,
            sentinel_content=sentinel_content,
            task_name=task_config.name,
            mutation_label=mutation_label,
        )

        # Step 4: Verify task completion independently of agent self-report
        verification_result = _verify_task(
            task_config=task_config,
            work_dir=work_dir,
        )

        # Ground-truth success: agent must report success AND verification passes.
        # If verification is not configured, fall back to agent self-report.
        if verification_result is not None:
            verified_success = verification_result.success
            if agent_result.success and not verified_success:
                log.warning(
                    "lifecycle_verification_failed_despite_agent_success",
                    task=task_config.name,
                    verify_command=task_config.verify_command,
                    verify_output=verification_result.raw_output[:500],
                )
            agent_result = AgentResult(
                success=verified_success,
                iterations_used=agent_result.iterations_used,
                tokens_used=agent_result.tokens_used,
                raw_output=(
                    agent_result.raw_output
                    + "\n\n--- VERIFICATION ---\n"
                    + verification_result.raw_output
                ),
                error_message=(
                    agent_result.error_message
                    if verified_success
                    else (
                        verification_result.raw_output[:500]
                        or agent_result.error_message
                    )
                ),
                execution_trace=agent_result.execution_trace,
            )

        elapsed = time.time() - start_time

        # Step 5: Save raw logs
        raw_log_path = save_raw_log(
            log_content=agent_result.raw_output,
            log_dir=log_dir,
            task_name=task_config.name,
            run_id=f"run_{run_index}_{int(start_time)}",
        )

        # Step 6: Build RunRecord
        record = collect_run_record(
            task_name=task_config.name,
            agent_name=agent.agent_name,
            agent_result=agent_result,
            runtime_seconds=elapsed,
            mutation_type=mutation_type,
            mutation_timing=MutationTiming.BEFORE if mutation_type else None,
            raw_log_path=str(raw_log_path),
        )

        log.info(
            "lifecycle_complete",
            task=task_config.name,
            mutation=mutation_label,
            success=record.success,
            runtime=round(elapsed, 2),
            run_id=record.run_id,
        )

        return record

    except Exception as exc:
        elapsed = time.time() - start_time
        log.exception(
            "lifecycle_failed",
            task=task_config.name,
            mutation=mutation_label,
            elapsed=round(elapsed, 2),
            error=str(exc),
        )

        # Create a failure record
        return RunRecord.create(
            task_name=task_config.name,
            agent_name=agent.agent_name,
            mutation_type=mutation_type,
            mutation_timing=MutationTiming.BEFORE if mutation_type else None,
            success=False,
            retry_count=0,
            runtime_seconds=elapsed,
            tokens_used=None,
            exception_count=1,
            first_failure_step=0,
            raw_log_path=None,
        )

    finally:
        # Step 6: Rollback mutation
        if mutation_applied and work_dir and mutation_spec:
            _rollback_mutation(work_dir, mutation_type, mutation_spec)

        # Step 7: Cleanup — keep the workdir if the run failed so the
        # operator can inspect exactly what state the agent left it in.
        # This is critical for diagnosing verification failures and
        # workspace access problems.
        if work_dir:
            # Determine if this run was a success by checking agent_result
            # Note: agent_result may not be bound if an early exception fired,
            # so we default to keeping the dir on any uncertainty.
            try:
                run_succeeded = agent_result.success  # type: ignore[possibly-undefined]
            except (NameError, AttributeError):
                run_succeeded = False

            if run_succeeded:
                cleanup_workdir(work_dir)
            else:
                log.warning(
                    "lifecycle_workdir_kept_for_inspection",
                    work_dir=str(work_dir),
                    task=task_config.name,
                    mutation=mutation_label,
                    reason="run_failed_or_verification_failed",
                )


def _load_and_apply_mutation(
    work_dir: Path,
    mutation_type: MutationType,
) -> MutationSpec:
    """Load the mutation spec and apply it to the working directory.

    Args:
        work_dir: Working copy of the task.
        mutation_type: Type of mutation to apply.

    Returns:
        The loaded MutationSpec (needed for rollback).

    Raises:
        LifecycleError: If the mutation cannot be loaded or applied.
    """
    log.info("lifecycle_mutation_loading", mutation=str(mutation_type))

    try:
        spec = get_mutation_spec(work_dir, mutation_type)
    except Exception as exc:
        raise LifecycleError(
            f"Failed to load mutation spec for '{mutation_type}' "
            f"from {work_dir}: {exc}"
        ) from exc

    log.info(
        "lifecycle_mutation_applying",
        mutation=str(mutation_type),
        description=spec.description,
        actions=len(spec.actions),
    )

    try:
        mutation = get_mutation(mutation_type)
        if not mutation.validate(work_dir, spec):
            raise LifecycleError(
                f"Mutation '{mutation_type}' validation failed. "
                f"Preconditions not met in {work_dir}."
            )
        mutation.apply(work_dir, spec)
        log.info("lifecycle_mutation_applied", mutation=str(mutation_type))
    except LifecycleError:
        raise
    except Exception as exc:
        raise LifecycleError(
            f"Failed to apply mutation '{mutation_type}': {exc}"
        ) from exc

    return spec


def _execute_agent(
    *,
    agent: BaseAgent,
    instruction: str,
    workspace_dir: str,
    max_iterations: int,
    timeout_seconds: int,
) -> AgentResult:
    """Execute the agent and return its result.

    Args:
        agent: Agent instance.
        instruction: Task instruction.
        workspace_dir: Path to workspace.
        max_iterations: Max agent iterations.
        timeout_seconds: Hard timeout.

    Returns:
        The agent's execution result.
    """
    log.info(
        "lifecycle_agent_executing",
        agent=agent.agent_name,
        max_iterations=max_iterations,
        timeout=timeout_seconds,
    )

    try:
        result = agent.execute_task(
            instruction=instruction,
            workspace_dir=workspace_dir,
            max_iterations=max_iterations,
            timeout_seconds=timeout_seconds,
        )
        log.info(
            "lifecycle_agent_finished",
            agent=agent.agent_name,
            success=result.success,
            iterations=result.iterations_used,
        )
        return result
    except AgentExecutionError as exc:
        log.error(
            "lifecycle_agent_error",
            agent=agent.agent_name,
            error=str(exc),
        )
        return AgentResult(
            success=False,
            iterations_used=0,
            tokens_used=None,
            raw_output=f"Agent execution error: {exc}",
            error_message=str(exc),
        )


def _validate_workspace_access(
    *,
    work_dir: Path,
    sentinel_path: Path,
    sentinel_content: str,
    task_name: str,
    mutation_label: str,
) -> None:
    """Check whether the agent actually operated on the correct work_dir.

    Writes a sentinel file before agent execution, then inspects afterward:
    - If the sentinel was deleted: agent definitely saw the workdir (good)
    - If the sentinel was modified: agent interacted with the workdir (good)
    - If no .py files were touched: agent may not have seen the workdir (bad)

    This check is diagnostic-only — it does NOT abort the run.  The result
    is logged as ``workspace_validated`` so it is visible in every run log.

    Args:
        work_dir: The working directory that was passed to the agent.
        sentinel_path: Path to the sentinel file that was written.
        sentinel_content: Original content of the sentinel file.
        task_name: Task name (for logging).
        mutation_label: Mutation label (for logging).
    """
    if not work_dir.exists():
        log.warning(
            "lifecycle_workspace_validation_skipped",
            reason="workdir_missing",
            task=task_name,
        )
        return

    # Check sentinel state
    sentinel_deleted = not sentinel_path.exists()
    sentinel_modified = False
    if sentinel_path.exists():
        try:
            current = sentinel_path.read_text(encoding="utf-8")
            sentinel_modified = current != sentinel_content
        except OSError:
            sentinel_modified = True

    # Count modified Python files (mtime newer than sentinel write)
    # This is a heuristic: if the agent fixed a bug, it changed .py files.
    sentinel_mtime = sentinel_path.stat().st_mtime if sentinel_path.exists() else 0.0
    try:
        modified_files = [
            str(p.relative_to(work_dir))
            for p in work_dir.rglob("*.py")
            if p.is_file() and p.stat().st_mtime > sentinel_mtime
        ]
    except OSError:
        modified_files = []

    workspace_validated = sentinel_deleted or sentinel_modified or bool(modified_files)

    log.info(
        "lifecycle_workspace_validation",
        task=task_name,
        mutation=mutation_label,
        workspace_validated=workspace_validated,
        sentinel_deleted=sentinel_deleted,
        sentinel_modified=sentinel_modified,
        modified_py_files=len(modified_files),
        modified_files_sample=modified_files[:5],
        work_dir=str(work_dir),
    )

    if not workspace_validated:
        log.warning(
            "lifecycle_workspace_not_validated",
            task=task_name,
            mutation=mutation_label,
            work_dir=str(work_dir),
            message=(
                "CRITICAL: No file changes detected in work_dir after agent execution. "
                "OpenHands may NOT be operating on this workspace. "
                "Benchmark results may be scientifically invalid."
            ),
        )


def _verify_task(
    *,
    task_config: TaskConfig,
    work_dir: Optional[Path],
) -> Optional[AgentResult]:
    """Run the task's verify_command and return an AgentResult-like outcome.

    This provides ground-truth success signal independent of the agent's
    self-reported result.  The command is executed on the HOST inside
    ``work_dir`` (the mutated working copy after the agent has run).

    Args:
        task_config: Task configuration containing ``verify_command``.
        work_dir: The working directory after agent execution.

    Returns:
        An AgentResult with ``success=True`` if exit code is 0, or
        ``success=False`` otherwise.  Returns ``None`` if there is no
        verify_command or work_dir is unavailable.
    """
    verify_cmd = task_config.verify_command.strip()
    if not verify_cmd or not work_dir or not work_dir.exists():
        log.debug(
            "lifecycle_verify_skip",
            task=task_config.name,
            reason="no_command_or_workdir",
        )
        return None

    log.info(
        "lifecycle_verifying",
        task=task_config.name,
        command=verify_cmd,
        work_dir=str(work_dir),
    )

    try:
        proc = subprocess.run(
            verify_cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(work_dir),
            timeout=60,
        )

        output = (proc.stdout + proc.stderr).strip()
        success = proc.returncode == 0

        log.info(
            "lifecycle_verify_complete",
            task=task_config.name,
            success=success,
            exit_code=proc.returncode,
            output_preview=output[:200],
        )

        return AgentResult(
            success=success,
            iterations_used=0,
            tokens_used=None,
            raw_output=(
                f"verify_command: {verify_cmd}\n"
                f"exit_code: {proc.returncode}\n"
                f"stdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            ),
            error_message=(
                None
                if success
                else f"Verification failed (exit={proc.returncode}): {output[:300]}"
            ),
        )

    except subprocess.TimeoutExpired:
        log.warning("lifecycle_verify_timeout", task=task_config.name)
        return AgentResult(
            success=False,
            iterations_used=0,
            tokens_used=None,
            raw_output=f"Verification timed out after 60s: {verify_cmd}",
            error_message="Verification timed out",
        )
    except Exception as exc:
        log.error(
            "lifecycle_verify_error",
            task=task_config.name,
            error=str(exc),
        )
        return AgentResult(
            success=False,
            iterations_used=0,
            tokens_used=None,
            raw_output=f"Verification error: {exc}",
            error_message=str(exc),
        )


def _rollback_mutation(
    work_dir: Path,
    mutation_type: Optional[MutationType],
    spec: MutationSpec,
) -> None:
    """Attempt to rollback a mutation. Failures are logged but not re-raised."""
    if mutation_type is None:
        return

    try:
        mutation = get_mutation(mutation_type)
        mutation.rollback(work_dir, spec)
        log.info("lifecycle_mutation_rolled_back", mutation=str(mutation_type))
    except Exception as exc:
        log.warning(
            "lifecycle_mutation_rollback_failed",
            mutation=str(mutation_type),
            error=str(exc),
        )
