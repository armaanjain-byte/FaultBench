from __future__ import annotations

from pathlib import Path

import pytest


def test_plugin_loads(pytestconfig: pytest.Config):
    """The faultbench plugin is registered."""
    plugin = pytestconfig.pluginmanager.get_plugin("faultbench")
    assert plugin is not None


def test_mutate_copies_and_cleans(tmp_path: Path, mutate):
    """mutate() copies the task dir and cleans up afterward."""
    task_dir = tmp_path / "sample_task"
    task_dir.mkdir()
    (task_dir / "file.txt").write_text("hello")

    with mutate(task_dir) as work_dir:
        assert work_dir.exists()
        assert (work_dir / "file.txt").read_text() == "hello"
        saved = work_dir.parent  # tmp_root

    assert not saved.exists()


def test_mutate_skipped_without_flag(pytester: pytest.Pytester):
    """Tests using the mutate fixture are skipped without --faultbench."""
    pytester.makepyfile(
        """
        from pathlib import Path

        def test_needs_mutate(tmp_path, mutate):
            with mutate(tmp_path) as w:
                assert w.exists()
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(skipped=1)


def test_marker_skipped_without_flag(pytester: pytest.Pytester):
    """Tests with @pytest.mark.faultbench are skipped without --faultbench."""
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.faultbench(mutation="schema_drift")
        def test_marked(faultbench_workdir):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(skipped=1)


def test_marker_cleanup_occurs(pytester: pytest.Pytester):
    """Workspace is cleaned up after a marker-based test completes."""
    pytester.makepyfile(
        """
        import pytest
        from pathlib import Path

        SAVED = []

        @pytest.fixture
        def faultbench_task_dir(tmp_path):
            task = tmp_path / "task"
            task.mkdir()
            (task / "schema.sql").write_text("CREATE TABLE users (id INT);")
            return task

        @pytest.mark.faultbench(mutation="schema_drift")
        def test_save_workdir(faultbench_workdir):
            SAVED.append(faultbench_workdir.parent)
            assert faultbench_workdir.exists()

        def test_verify_cleanup():
            assert len(SAVED) == 1
            assert not SAVED[0].exists()
        """
    )
    result = pytester.runpytest("--faultbench", "-v")
    result.assert_outcomes(passed=2)


def test_nonfaultbench_tests_unaffected(pytester: pytest.Pytester):
    """Normal tests run regardless of --faultbench flag."""
    pytester.makepyfile(
        """
        def test_normal():
            assert 1 + 1 == 2
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)

    result2 = pytester.runpytest("--faultbench")
    result2.assert_outcomes(passed=1)
