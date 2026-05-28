from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent))
from client import process_user


@pytest.fixture
def faultbench_task_dir() -> Path:
    return Path(__file__).parent


def test_baseline_api_contract(faultbench_task_dir: Path):
    """The application works normally when the API adheres to the contract."""
    result = process_user(faultbench_task_dir)
    assert "Processed user 123 (Alice)" in result


@pytest.mark.faultbench(mutation="config_drift", expect_failure=True)
def test_api_contract_drift_detected(faultbench_workdir: Path):
    """
    If the API response payload changes unexpectedly (e.g. user_id -> id),
    the application MUST detect it and fail explicitly due to a contract violation.
    """
    with pytest.raises(KeyError, match="API Contract Violation: missing 'user_id'"):
        process_user(faultbench_workdir)


@pytest.mark.faultbench(mutation="malformed_config", expect_failure=True)
def test_api_contract_malformed_response(faultbench_workdir: Path):
    """
    If the downstream API drops connection mid-stream or returns an HTML 502 page,
    the application should gracefully catch the parsing error rather than crashing deeply.
    """
    with pytest.raises(ValueError, match="API returned malformed JSON"):
        process_user(faultbench_workdir)
