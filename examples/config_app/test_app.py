from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app import get_database_url


EXAMPLE_DIR = Path(__file__).parent


@pytest.fixture
def faultbench_task_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "config_app"
    shutil.copytree(EXAMPLE_DIR, dest)
    return dest


def test_database_url_loads(tmp_path: Path):
    dest = tmp_path / "config_app"
    shutil.copytree(EXAMPLE_DIR, dest)
    assert get_database_url(dest) == "sqlite:///app.db"


@pytest.mark.faultbench(mutation="config_drift")
def test_config_drift_causes_missing_database_url(faultbench_workdir: Path):
    with pytest.raises(RuntimeError, match="DATABASE_URL missing"):
        get_database_url(faultbench_workdir)


@pytest.mark.faultbench(mutation="malformed_config")
def test_malformed_config_causes_json_parse_failure(faultbench_workdir: Path):
    with pytest.raises(json.JSONDecodeError):
        get_database_url(faultbench_workdir)
