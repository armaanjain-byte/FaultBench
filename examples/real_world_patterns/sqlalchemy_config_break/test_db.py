from pathlib import Path
import pytest
import sys

# Add the current directory to sys.path so we can import app
sys.path.insert(0, str(Path(__file__).parent))
from app import connect_db


@pytest.fixture
def faultbench_task_dir() -> Path:
    return Path(__file__).parent


def test_baseline_startup(faultbench_task_dir: Path):
    """The application should start up normally using the baseline config."""
    result = connect_db(faultbench_task_dir)
    assert "sqlite:///app.db" in result


@pytest.mark.faultbench(mutation="config_drift", expect_failure=True)
def test_config_drift_caught_at_startup(faultbench_workdir: Path):
    """
    If the configuration file structure drifts in production (e.g., DATABASE_URL is renamed),
    the application MUST crash loudly instead of booting in a broken state.
    """
    with pytest.raises(ValueError, match="DATABASE_URL missing from configuration"):
        connect_db(faultbench_workdir)
