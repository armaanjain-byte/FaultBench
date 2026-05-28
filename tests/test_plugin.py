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
