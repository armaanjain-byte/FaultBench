"""Typed configuration loader for FaultBench.

Loads ``config.yaml``, applies environment variable overrides, and
returns a fully typed :class:`BenchmarkConfig` dataclass.  This is the
only module that reads the YAML file — all other code receives the
config object by injection.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from faultbench.constants import DEFAULT_CONFIG_PATH
from faultbench.logging import get_logger
from faultbench.models import (
    AgentConfig,
    BenchmarkConfig,
    BenchmarkSettings,
    PathsConfig,
    SandboxConfig,
)

log = get_logger(__name__)

# Module-level cache so repeated calls return the same object
_cached_config: Optional[BenchmarkConfig] = None


def _deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to raw config dict.

    Supported overrides:
        FAULTBENCH_MODEL          → agent.model
        FAULTBENCH_MAX_ITERATIONS → agent.max_iterations
        FAULTBENCH_DB_PATH        → paths.db
        FAULTBENCH_LOG_DIR        → paths.logs
        FAULTBENCH_SANDBOX_IMAGE  → sandbox.image
        FAULTBENCH_MEMORY_LIMIT   → sandbox.memory_limit
        FAULTBENCH_MAX_RUNTIME    → sandbox.max_runtime_seconds
    """
    overrides: list[tuple[str, tuple[str, ...], type]] = [
        ("FAULTBENCH_OPENHANDS_BASE_URL", ("agent", "base_url"), str),
        ("FAULTBENCH_MODEL", ("agent", "model"), str),
        ("FAULTBENCH_MAX_ITERATIONS", ("agent", "max_iterations"), int),
        ("FAULTBENCH_DB_PATH", ("paths", "db"), str),
        ("FAULTBENCH_LOG_DIR", ("paths", "logs"), str),
        ("FAULTBENCH_SANDBOX_IMAGE", ("sandbox", "image"), str),
        ("FAULTBENCH_MEMORY_LIMIT", ("sandbox", "memory_limit"), str),
        ("FAULTBENCH_MAX_RUNTIME", ("sandbox", "max_runtime_seconds"), int),
    ]

    for env_key, path_keys, cast_type in overrides:
        env_val = os.environ.get(env_key)
        if env_val is not None:
            section = raw
            for key in path_keys[:-1]:
                section = section.setdefault(key, {})
            section[path_keys[-1]] = cast_type(env_val)
            log.debug("config_env_override", env_key=env_key, value=env_val)

    return raw


def _build_agent_config(raw: dict[str, Any]) -> AgentConfig:
    """Construct ``AgentConfig`` from the ``agent:`` section."""
    section = raw.get("agent", {})
    if not isinstance(section, dict):
        section = {}
    return AgentConfig(
        default=section.get("default", "openhands"),
        base_url=section.get("base_url", "http://localhost:3000"),
        model=section.get("model", "claude-sonnet-4-20250514"),
        max_iterations=int(section.get("max_iterations", 30)),
        poll_interval_seconds=float(section.get("poll_interval_seconds", 5.0)),
        start_task_timeout_seconds=float(
            section.get("start_task_timeout_seconds", 120.0)
        ),
    )


def _build_sandbox_config(raw: dict[str, Any]) -> SandboxConfig:
    """Construct ``SandboxConfig`` from the ``sandbox:`` section."""
    section = raw.get("sandbox", {})
    if not isinstance(section, dict):
        section = {}
    return SandboxConfig(
        image=section.get("image", "faultbench-sandbox:latest"),
        memory_limit=section.get("memory_limit", "512m"),
        cpu_quota=int(section.get("cpu_quota", 50_000)),
        max_runtime_seconds=int(section.get("max_runtime_seconds", 900)),
    )


def _build_paths_config(raw: dict[str, Any]) -> PathsConfig:
    """Construct ``PathsConfig`` from the ``paths:`` section."""
    section = raw.get("paths", {})
    if not isinstance(section, dict):
        section = {}
    return PathsConfig(
        db=section.get("db", "db/faultbench.db"),
        logs=section.get("logs", "logs/"),
        reports=section.get("reports", "reports/"),
        tasks=section.get("tasks", "tasks/"),
    )


def _build_benchmark_settings(raw: dict[str, Any]) -> BenchmarkSettings:
    """Construct ``BenchmarkSettings`` from the ``benchmark:`` section."""
    section = raw.get("benchmark", {})
    if not isinstance(section, dict):
        section = {}
    return BenchmarkSettings(
        min_runs_for_comparison=int(section.get("min_runs_for_comparison", 5)),
        default_runs=int(section.get("default_runs", 10)),
    )


def load_config(path: Optional[str] = None, *, force_reload: bool = False) -> BenchmarkConfig:
    """Load and cache the benchmark configuration.

    Args:
        path: Path to the YAML config file.  Defaults to ``config.yaml``
              in the current working directory.
        force_reload: If ``True``, bypass the module-level cache and
                      re-read from disk.

    Returns:
        A fully populated :class:`BenchmarkConfig` dataclass.

    Raises:
        FileNotFoundError: If the config file does not exist.
        yaml.YAMLError: If the YAML is malformed.
        ValueError: If critical fields have invalid values.
    """
    global _cached_config

    if _cached_config is not None and not force_reload:
        return _cached_config

    config_path = Path(path or DEFAULT_CONFIG_PATH)

    if not config_path.exists():
        log.warning(
            "config_file_missing",
            path=str(config_path),
            action="using_defaults",
        )
        _cached_config = BenchmarkConfig()
        return _cached_config

    log.info("config_loading", path=str(config_path))

    with open(config_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if raw is None:
        log.warning("config_file_empty", path=str(config_path), action="using_defaults")
        raw = {}

    if not isinstance(raw, dict):
        raise ValueError(
            f"Config file must contain a YAML mapping, got {type(raw).__name__}"
        )

    raw = _apply_env_overrides(raw)

    config = BenchmarkConfig(
        agent=_build_agent_config(raw),
        sandbox=_build_sandbox_config(raw),
        paths=_build_paths_config(raw),
        benchmark=_build_benchmark_settings(raw),
    )

    log.info(
        "config_loaded",
        agent=config.agent.default,
        model=config.agent.model,
        db_path=config.paths.db,
        sandbox_image=config.sandbox.image,
    )

    _cached_config = config
    return config


def reset_config_cache() -> None:
    """Clear the cached config.  Useful in tests."""
    global _cached_config
    _cached_config = None
