from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import CONFIG_PATH, create_app


@pytest.fixture
def faultbench_task_dir() -> Path:
    return CONFIG_PATH.parent


def test_health_baseline():
    client = create_app().test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


@pytest.mark.faultbench(mutation="config_drift")
def test_config_drift_breaks_startup(faultbench_workdir: Path):
    with pytest.raises(RuntimeError, match="DATABASE_URL missing"):
        create_app(faultbench_workdir / "config.json")


@pytest.mark.faultbench(mutation="malformed_config")
def test_malformed_config_breaks_json_loading(faultbench_workdir: Path):
    with pytest.raises(json.JSONDecodeError):
        create_app(faultbench_workdir / "config.json")
