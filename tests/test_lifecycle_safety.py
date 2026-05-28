"""Tests for lifecycle hardening and nested exception safety."""

from __future__ import annotations

import pytest


def test_rollback_executes_after_test_failure(pytester: pytest.Pytester):
    """If a test fails, rollback should still execute."""
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def faultbench_task_dir(tmp_path):
            task = tmp_path / "task"
            task.mkdir()
            (task / "schema.sql").write_text("CREATE TABLE users (id INT);")
            return task

        @pytest.mark.faultbench(mutation="schema_drift")
        def test_fails(faultbench_workdir):
            assert False, "forced failure"
        """
    )
    result = pytester.runpytest("--faultbench")
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines([
        "*Rollback successful: YES*",
    ])


def test_rollback_failure_does_not_crash_session(pytester: pytest.Pytester):
    """If rollback fails, it should be caught, record NO in summary, and print warning."""
    pytester.makepyfile(
        """
        import pytest
        from pytest_faultbench.mutations.schema_drift import SchemaDriftMutation

        @pytest.fixture(autouse=True)
        def break_rollback(monkeypatch):
            def bad_rollback(self, workdir):
                raise RuntimeError("Boom!")
            monkeypatch.setattr(SchemaDriftMutation, "rollback", bad_rollback)

        @pytest.fixture
        def faultbench_task_dir(tmp_path):
            task = tmp_path / "task"
            task.mkdir()
            (task / "schema.sql").write_text("CREATE TABLE users (id INT);")
            return task

        @pytest.mark.faultbench(mutation="schema_drift")
        def test_pass(faultbench_workdir):
            pass

        @pytest.mark.faultbench(mutation="schema_drift")
        def test_another(faultbench_workdir):
            pass
        """
    )
    result = pytester.runpytest("--faultbench", "-s")
    result.assert_outcomes(passed=2)
    result.stderr.fnmatch_lines([
        "*Rollback failed for mutation: schema_drift*",
    ])
    result.stdout.fnmatch_lines([
        "*Rollback successful: NO*",
    ])


def test_cleanup_failure_does_not_abort_remaining(pytester: pytest.Pytester):
    """If workspace cleanup fails, a warning is printed but session continues."""
    pytester.makepyfile(
        """
        import pytest
        import pytest_faultbench.plugin

        @pytest.fixture(autouse=True)
        def break_cleanup(monkeypatch):
            def bad_remove(path):
                raise RuntimeError("Cannot remove")
            monkeypatch.setattr(pytest_faultbench.plugin, "remove", bad_remove)

        @pytest.fixture
        def faultbench_task_dir(tmp_path):
            task = tmp_path / "task"
            task.mkdir()
            (task / "schema.sql").write_text("CREATE TABLE users (id INT);")
            return task

        @pytest.mark.faultbench(mutation="schema_drift")
        def test_one(faultbench_workdir):
            pass

        @pytest.mark.faultbench(mutation="schema_drift")
        def test_two(faultbench_workdir):
            pass
        """
    )
    result = pytester.runpytest("--faultbench", "-s")
    result.assert_outcomes(passed=2)
    result.stderr.fnmatch_lines([
        "*Cleanup failed for workspace:*",
    ])


def test_original_workspace_remains_unchanged(tmp_path, mutate):
    """Verify mutation only applies to copied dir, not source dir."""
    task = tmp_path / "task"
    task.mkdir()
    (task / "schema.sql").write_text("CREATE TABLE users (id INT);")
    
    with mutate(task, mutation="schema_drift") as workdir:
        mutated_schema = (workdir / "schema.sql").read_text()
        assert mutated_schema != "CREATE TABLE users (id INT);"
        # Original is untouched
        assert (task / "schema.sql").read_text() == "CREATE TABLE users (id INT);"
        
    assert (task / "schema.sql").read_text() == "CREATE TABLE users (id INT);"


def test_mutation_apply_failure_handled_safely(pytester: pytest.Pytester):
    """If mutation apply() raises, test fails as Error but session continues."""
    pytester.makepyfile(
        """
        import pytest
        from pytest_faultbench.mutations.schema_drift import SchemaDriftMutation

        @pytest.fixture(autouse=True)
        def break_apply(monkeypatch):
            def bad_apply(self, workdir):
                raise RuntimeError("Apply Boom!")
            monkeypatch.setattr(SchemaDriftMutation, "apply", bad_apply)

        @pytest.fixture
        def faultbench_task_dir(tmp_path):
            task = tmp_path / "task"
            task.mkdir()
            (task / "schema.sql").write_text("CREATE TABLE users (id INT);")
            return task

        @pytest.mark.faultbench(mutation="schema_drift")
        def test_one(faultbench_workdir):
            pass
            
        def test_normal():
            pass
        """
    )
    result = pytester.runpytest("--faultbench", "-s")
    result.assert_outcomes(errors=1, passed=1)
