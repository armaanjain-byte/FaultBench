from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pytest_faultbench.mutations.config_drift import ConfigDriftMutation
from pytest_faultbench.mutations.malformed_config import MalformedConfigMutation


SAMPLE_CONFIG = """\
{
  "DATABASE_URL": "sqlite:///app.db"
}
"""

DRIFTED_CONFIG = """\
{
  "DB_URL": "sqlite:///app.db"
}
"""

MALFORMED_CONFIG = """\
{
  "DATABASE_URL": "sqlite:///app.db"

"""


def _make_task(tmp_path: Path, config: str = SAMPLE_CONFIG) -> Path:
    task = tmp_path / "task"
    task.mkdir()
    (task / "config.json").write_text(config)
    return task


class TestConfigDriftMutation:
    def test_apply_mutates_config_key(self, tmp_path: Path):
        task = _make_task(tmp_path)
        m = ConfigDriftMutation()
        m.apply(task)
        assert (task / "config.json").read_text() == DRIFTED_CONFIG

    def test_rollback_restores_original(self, tmp_path: Path):
        task = _make_task(tmp_path)
        m = ConfigDriftMutation()
        m.apply(task)
        m.rollback(task)
        assert (task / "config.json").read_text() == SAMPLE_CONFIG

    def test_missing_config_raises(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        m = ConfigDriftMutation()
        with pytest.raises(RuntimeError, match="config.json not found"):
            m.apply(empty)

    def test_missing_database_url_raises(self, tmp_path: Path):
        task = _make_task(tmp_path, '{"DB_URL": "sqlite:///app.db"}\n')
        m = ConfigDriftMutation()
        with pytest.raises(RuntimeError, match="DATABASE_URL not found"):
            m.apply(task)


class TestMalformedConfigMutation:
    def test_apply_removes_final_closing_brace(self, tmp_path: Path):
        task = _make_task(tmp_path)
        m = MalformedConfigMutation()
        m.apply(task)
        assert (task / "config.json").read_text() == MALFORMED_CONFIG

    def test_rollback_restores_original(self, tmp_path: Path):
        task = _make_task(tmp_path)
        m = MalformedConfigMutation()
        m.apply(task)
        m.rollback(task)
        assert (task / "config.json").read_text() == SAMPLE_CONFIG

    def test_mutated_config_is_malformed_json(self, tmp_path: Path):
        task = _make_task(tmp_path)
        m = MalformedConfigMutation()
        m.apply(task)
        with pytest.raises(json.JSONDecodeError):
            json.loads((task / "config.json").read_text())

    def test_missing_config_raises(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        m = MalformedConfigMutation()
        with pytest.raises(RuntimeError, match="config.json not found"):
            m.apply(empty)


class TestMutateFixtureWithConfigMutations:
    def test_config_drift_applied_inside_context(self, tmp_path: Path, mutate):
        task = _make_task(tmp_path)
        with mutate(task, mutation="config_drift") as work_dir:
            assert (work_dir / "config.json").read_text() == DRIFTED_CONFIG

    def test_malformed_config_applied_inside_context(self, tmp_path: Path, mutate):
        task = _make_task(tmp_path)
        with mutate(task, mutation="malformed_config") as work_dir:
            assert (work_dir / "config.json").read_text() == MALFORMED_CONFIG

    def test_cleanup_after_failure(self, tmp_path: Path, mutate):
        task = _make_task(tmp_path)
        saved_root = None
        with pytest.raises(ValueError, match="boom"):
            with mutate(task, mutation="malformed_config") as work_dir:
                saved_root = work_dir.parent
                raise ValueError("boom")
        assert saved_root is not None
        assert not saved_root.exists()

    def test_original_workspace_untouched(self, tmp_path: Path, mutate):
        task = _make_task(tmp_path)
        with mutate(task, mutation="config_drift") as work_dir:
            assert (work_dir / "config.json").read_text() == DRIFTED_CONFIG
        assert (task / "config.json").read_text() == SAMPLE_CONFIG


@pytest.fixture
def faultbench_task_dir(tmp_path: Path) -> Path:
    return _make_task(tmp_path)


class TestMarkerBasedConfigMutations:
    @pytest.mark.faultbench(mutation="config_drift")
    def test_config_drift_marker_mutates_workdir(self, faultbench_workdir: Path):
        assert (faultbench_workdir / "config.json").read_text() == DRIFTED_CONFIG

    @pytest.mark.faultbench(mutation="malformed_config")
    def test_malformed_config_marker_mutates_workdir(self, faultbench_workdir: Path):
        assert (faultbench_workdir / "config.json").read_text() == MALFORMED_CONFIG


EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "config_app"


@pytest.fixture
def example_task_dir(tmp_path: Path) -> Path:
    dest = tmp_path / "config_app"
    shutil.copytree(EXAMPLE_DIR, dest)
    return dest


class TestConfigExampleIntegration:
    @staticmethod
    def _load_get_database_url():
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "config_app", EXAMPLE_DIR / "app.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_database_url

    def test_example_baseline_passes(self, example_task_dir: Path):
        get_database_url = self._load_get_database_url()
        assert get_database_url(example_task_dir) == "sqlite:///app.db"

    def test_example_config_drift_breaks_lookup(self, example_task_dir: Path, mutate):
        get_database_url = self._load_get_database_url()
        with mutate(example_task_dir, mutation="config_drift") as work_dir:
            with pytest.raises(RuntimeError, match="DATABASE_URL missing"):
                get_database_url(work_dir)

    def test_example_malformed_config_breaks_parsing(
        self, example_task_dir: Path, mutate
    ):
        get_database_url = self._load_get_database_url()
        with mutate(example_task_dir, mutation="malformed_config") as work_dir:
            with pytest.raises(json.JSONDecodeError):
                get_database_url(work_dir)
