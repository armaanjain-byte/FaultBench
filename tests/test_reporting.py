from __future__ import annotations

import pytest

from pytest_faultbench.reporting import MutationReport, render_terminal_summary


def test_summary_renders_correctly():
    summary = render_terminal_summary(
        [
            MutationReport(
                mutation_name="schema_drift",
                tests_affected=2,
                failures_detected=True,
                rollback_successful=True,
            ),
            MutationReport(
                mutation_name="malformed_config",
                tests_affected=1,
                failures_detected=True,
                rollback_successful=True,
            ),
        ]
    )

    assert "================ FaultBench Summary ================" in summary
    assert "Mutation: schema_drift" in summary
    assert "Tests affected: 2" in summary
    assert "Failures detected: YES" in summary
    assert "Rollback successful: YES" in summary
    assert "Mutation: malformed_config" in summary


def test_failure_detection_works(pytester: pytest.Pytester):
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
        def test_detects_mutation(faultbench_workdir):
            assert False
        """
    )

    result = pytester.runpytest("--faultbench")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*FaultBench Summary*",
            "Mutation: schema_drift",
            "Tests affected: 1",
            "Failures detected: YES",
            "Rollback successful: YES",
        ]
    )


def test_no_failure_mutation_reports_no(pytester: pytest.Pytester):
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
        def test_survives_mutation(faultbench_workdir):
            assert faultbench_workdir.exists()
        """
    )

    result = pytester.runpytest("--faultbench")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        [
            "*FaultBench Summary*",
            "Mutation: schema_drift",
            "Tests affected: 1",
            "Failures detected: NO",
            "Rollback successful: YES",
        ]
    )


def test_rollback_status_displayed():
    summary = render_terminal_summary(
        [
            MutationReport(
                mutation_name="schema_drift",
                tests_affected=1,
                failures_detected=False,
                rollback_successful=False,
            )
        ]
    )

    assert "Rollback successful: NO" in summary
