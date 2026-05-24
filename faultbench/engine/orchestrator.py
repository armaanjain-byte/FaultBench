"""Multi-run benchmark orchestrator for FaultBench.

Coordinates execution of multiple benchmark runs across tasks and
mutation conditions.  This is the top-level engine that the CLI
delegates to.

Responsibilities:
- Load task configurations from ``tasks/`` directory
- Schedule baseline and mutated runs
- Delegate individual runs to the lifecycle manager
- Persist results to the database
- Log progress and summary statistics
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from faultbench.agent.base import BaseAgent
from faultbench.agent.openhands_client import OpenHandsClient
from faultbench.config import load_config
from faultbench.constants import AgentName, MutationType
from faultbench.db.store import BenchmarkStore
from faultbench.engine.lifecycle import execute_single_run
from faultbench.logging import get_logger
from faultbench.models import BenchmarkConfig, RunRecord, TaskConfig

log = get_logger(__name__)


class OrchestratorError(Exception):
    """Raised when orchestration-level errors occur."""


def _create_agent(config: BenchmarkConfig) -> BaseAgent:
    """Instantiate the configured agent.

    Args:
        config: Benchmark configuration.

    Returns:
        An agent instance ready to execute tasks.

    Raises:
        OrchestratorError: If the configured agent is not supported.
    """
    agent_name = config.agent.default.lower()

    if agent_name == AgentName.OPENHANDS.value:
        return OpenHandsClient(
            model=config.agent.model,
            poll_interval=config.agent.poll_interval_seconds,
        )

    raise OrchestratorError(
        f"Unsupported agent: '{agent_name}'. "
        f"Supported agents: {[a.value for a in AgentName]}"
    )


def load_task_configs(tasks_dir: Path) -> list[TaskConfig]:
    """Discover and load all task configurations from the tasks directory.

    Scans for directories containing a ``task.yaml`` file.

    Args:
        tasks_dir: Base directory containing task subdirectories.

    Returns:
        List of loaded TaskConfig objects.

    Raises:
        FileNotFoundError: If the tasks directory doesn't exist.
    """
    if not tasks_dir.exists():
        raise FileNotFoundError(f"Tasks directory not found: {tasks_dir}")

    task_configs: list[TaskConfig] = []

    for task_dir in sorted(tasks_dir.iterdir()):
        if not task_dir.is_dir():
            continue

        task_yaml = task_dir / "task.yaml"
        if not task_yaml.exists():
            log.debug("task_skip_no_yaml", dir=str(task_dir))
            continue

        try:
            with open(task_yaml, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)

            if not isinstance(raw, dict):
                log.warning("task_invalid_yaml", path=str(task_yaml))
                continue

            # Parse valid mutations
            valid_mutation_strs = raw.get("valid_mutations", [])
            valid_mutations: list[MutationType] = []
            for m_str in valid_mutation_strs:
                try:
                    valid_mutations.append(MutationType(m_str))
                except ValueError:
                    log.warning(
                        "task_invalid_mutation",
                        task=raw.get("name", task_dir.name),
                        mutation=m_str,
                    )

            task_config = TaskConfig(
                name=raw.get("name", task_dir.name),
                description=raw.get("description", ""),
                instruction=raw.get("instruction", ""),
                repo_path=str(task_dir.resolve()),
                verify_command=raw.get("verify_command", f"cd {task_dir} && bash verify.sh"),
                valid_mutations=valid_mutations,
                timeout_seconds=int(raw.get("timeout_seconds", 900)),
            )

            task_configs.append(task_config)
            log.info(
                "task_loaded",
                name=task_config.name,
                mutations=len(task_config.valid_mutations),
            )

        except Exception as exc:
            log.error(
                "task_load_failed",
                path=str(task_yaml),
                error=str(exc),
            )

    log.info("tasks_discovery_complete", total=len(task_configs))
    return task_configs


def run_benchmark(
    *,
    config_path: Optional[str] = None,
    task_filter: Optional[str] = None,
    mutation_filter: Optional[str] = None,
    num_runs: Optional[int] = None,
    baseline_only: bool = False,
    mutations_only: bool = False,
) -> list[RunRecord]:
    """Run a full benchmark suite.

    This is the main entry point called by the CLI.

    Args:
        config_path: Path to config.yaml (uses default if None).
        task_filter: If set, only run tasks matching this name.
        mutation_filter: If set, only run this mutation type.
        num_runs: Number of runs per condition (overrides config).
        baseline_only: If True, skip mutated runs.
        mutations_only: If True, skip baseline runs.

    Returns:
        List of all RunRecord objects produced.
    """
    config = load_config(config_path)
    tasks_dir = Path(config.paths.tasks)
    runs_per_condition = num_runs or config.benchmark.default_runs

    log.info(
        "benchmark_start",
        tasks_dir=str(tasks_dir),
        runs_per_condition=runs_per_condition,
        task_filter=task_filter,
        mutation_filter=mutation_filter,
        baseline_only=baseline_only,
        mutations_only=mutations_only,
    )

    # Load tasks
    all_tasks = load_task_configs(tasks_dir)
    if task_filter:
        all_tasks = [t for t in all_tasks if task_filter in t.name]

    if not all_tasks:
        log.warning("benchmark_no_tasks", tasks_dir=str(tasks_dir))
        return []

    # Create agent
    agent = _create_agent(config)

    # Open database
    all_records: list[RunRecord] = []
    with BenchmarkStore(config.paths.db) as store:
        for task in all_tasks:
            task_records = _run_task_conditions(
                task=task,
                agent=agent,
                config=config,
                store=store,
                runs_per_condition=runs_per_condition,
                mutation_filter=mutation_filter,
                baseline_only=baseline_only,
                mutations_only=mutations_only,
            )
            all_records.extend(task_records)

    log.info(
        "benchmark_complete",
        total_runs=len(all_records),
        successes=sum(1 for r in all_records if r.success),
    )

    return all_records


def _run_task_conditions(
    *,
    task: TaskConfig,
    agent: BaseAgent,
    config: BenchmarkConfig,
    store: BenchmarkStore,
    runs_per_condition: int,
    mutation_filter: Optional[str] = None,
    baseline_only: bool = False,
    mutations_only: bool = False,
) -> list[RunRecord]:
    """Run all conditions (baseline + mutations) for a single task.

    Args:
        task: Task configuration.
        agent: Agent instance.
        config: Global config.
        store: Database store.
        runs_per_condition: How many times to repeat each condition.
        mutation_filter: Optional mutation type filter.
        baseline_only: Skip mutations if True.
        mutations_only: Skip baseline if True.

    Returns:
        List of RunRecord objects for this task.
    """
    records: list[RunRecord] = []

    log.info(
        "task_benchmark_start",
        task=task.name,
        runs_per_condition=runs_per_condition,
    )

    # Baseline runs
    if not mutations_only:
        log.info("task_baseline_runs_start", task=task.name, count=runs_per_condition)
        for i in range(runs_per_condition):
            record = execute_single_run(
                task_config=task,
                agent=agent,
                config=config,
                mutation_type=None,
                run_index=i,
            )
            store.insert_run(record)
            records.append(record)
            log.info(
                "task_baseline_run_complete",
                task=task.name,
                run=i + 1,
                total=runs_per_condition,
                success=record.success,
            )

    # Mutated runs
    if not baseline_only:
        mutations_to_run = task.valid_mutations
        if mutation_filter:
            try:
                target_mutation = MutationType(mutation_filter)
                mutations_to_run = [
                    m for m in mutations_to_run if m == target_mutation
                ]
            except ValueError:
                log.warning(
                    "invalid_mutation_filter",
                    filter=mutation_filter,
                    valid=[str(m) for m in MutationType],
                )
                mutations_to_run = []

        for mutation_type in mutations_to_run:
            log.info(
                "task_mutation_runs_start",
                task=task.name,
                mutation=str(mutation_type),
                count=runs_per_condition,
            )
            for i in range(runs_per_condition):
                record = execute_single_run(
                    task_config=task,
                    agent=agent,
                    config=config,
                    mutation_type=mutation_type,
                    run_index=i,
                )
                store.insert_run(record)
                records.append(record)
                log.info(
                    "task_mutation_run_complete",
                    task=task.name,
                    mutation=str(mutation_type),
                    run=i + 1,
                    total=runs_per_condition,
                    success=record.success,
                )

    log.info(
        "task_benchmark_complete",
        task=task.name,
        total_runs=len(records),
        successes=sum(1 for r in records if r.success),
    )

    return records
