from __future__ import annotations

from pathlib import Path

import pytest

from pytest_faultbench.mutations.schema_drift import SchemaDriftMutation

SAMPLE_SQL = """\
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
"""

EXPECTED_MUTATED = """\
CREATE TABLE users_v2 (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);
"""


def _make_task(tmp_path: Path, sql: str = SAMPLE_SQL) -> Path:
    """Create a minimal task dir with a schema.sql."""
    task = tmp_path / "task"
    task.mkdir()
    (task / "schema.sql").write_text(sql)
    return task


class TestSchemaDriftMutation:
    def test_apply_mutates_schema(self, tmp_path: Path):
        task = _make_task(tmp_path)
        m = SchemaDriftMutation()
        m.apply(task)
        assert (task / "schema.sql").read_text() == EXPECTED_MUTATED

    def test_rollback_restores_original(self, tmp_path: Path):
        task = _make_task(tmp_path)
        m = SchemaDriftMutation()
        m.apply(task)
        m.rollback(task)
        assert (task / "schema.sql").read_text() == SAMPLE_SQL

    def test_missing_schema_raises(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        m = SchemaDriftMutation()
        with pytest.raises(RuntimeError, match="schema.sql not found"):
            m.apply(empty)


class TestMutateFixtureWithMutation:
    def test_mutation_applied_inside_context(self, tmp_path: Path, mutate):
        task = _make_task(tmp_path)
        with mutate(task, mutation="schema_drift") as work_dir:
            assert (work_dir / "schema.sql").read_text() == EXPECTED_MUTATED

    def test_rollback_after_context(self, tmp_path: Path, mutate):
        task = _make_task(tmp_path)
        with mutate(task, mutation="schema_drift") as work_dir:
            mutated_path = work_dir / "schema.sql"
            assert "users_v2" in mutated_path.read_text()
        # work_dir is cleaned up, but verify rollback ran by checking
        # the original task dir is untouched
        assert (task / "schema.sql").read_text() == SAMPLE_SQL

    def test_cleanup_after_failure(self, tmp_path: Path, mutate):
        task = _make_task(tmp_path)
        saved_root = None
        with pytest.raises(ValueError, match="boom"):
            with mutate(task, mutation="schema_drift") as work_dir:
                saved_root = work_dir.parent
                raise ValueError("boom")
        assert not saved_root.exists()

    def test_no_mutation_still_works(self, tmp_path: Path, mutate):
        task = _make_task(tmp_path)
        with mutate(task) as work_dir:
            assert (work_dir / "schema.sql").read_text() == SAMPLE_SQL


# ---------------------------------------------------------------------------
# Marker-based tests
# ---------------------------------------------------------------------------

@pytest.fixture
def faultbench_task_dir(tmp_path: Path) -> Path:
    """User-provided task dir for marker-based mutation tests."""
    return _make_task(tmp_path)


class TestMarkerBasedMutation:
    @pytest.mark.faultbench(mutation="schema_drift")
    def test_workdir_exists(self, faultbench_workdir: Path):
        assert faultbench_workdir.exists()
        assert faultbench_workdir.is_dir()

    @pytest.mark.faultbench(mutation="schema_drift")
    def test_schema_is_mutated(self, faultbench_workdir: Path):
        assert (faultbench_workdir / "schema.sql").read_text() == EXPECTED_MUTATED

    @pytest.mark.faultbench()
    def test_no_mutation_preserves_schema(self, faultbench_workdir: Path):
        assert (faultbench_workdir / "schema.sql").read_text() == SAMPLE_SQL

    @pytest.mark.faultbench(mutation="schema_drift")
    def test_original_task_dir_untouched(self, faultbench_workdir: Path, faultbench_task_dir: Path):
        """Mutation only affects copied workspace, not the source."""
        assert (faultbench_task_dir / "schema.sql").read_text() == SAMPLE_SQL
