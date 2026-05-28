import json
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent))
from app import start_app


@pytest.fixture
def faultbench_task_dir() -> Path:
    return Path(__file__).parent


def _load_env_from_workspace(work_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Simulate a deployment orchestrator passing files as env vars to the app."""
    config_path = work_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        for k, v in config.items():
            monkeypatch.setenv(k, str(v))


def test_baseline_env(faultbench_task_dir: Path, monkeypatch: pytest.MonkeyPatch):
    _load_env_from_workspace(faultbench_task_dir, monkeypatch)
    result = start_app()
    assert "sqlite:///production.db" in result


@pytest.mark.faultbench(mutation="config_drift", expect_failure=True)
def test_env_var_drift_caught(faultbench_workdir: Path, monkeypatch: pytest.MonkeyPatch):
    """
    If the deployment environment variable is renamed (e.g. DATABASE_URL -> DB_URL),
    the application MUST crash because it strictly requires DATABASE_URL.
    """
    # Load the mutated workspace config into the environment
    _load_env_from_workspace(faultbench_workdir, monkeypatch)
    
    with pytest.raises(RuntimeError, match="Missing required environment variable: DATABASE_URL"):
        start_app()
