"""Tests for the CSV data pipeline — validates running-total correctness."""
from __future__ import annotations

import json
import os
import sys

import pytest

# Ensure the task root is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from transformers import clean_row, calculate_running_totals  # noqa: E402
from validators import validate_row, validate_numeric  # noqa: E402
from pipeline import read_csv, run_pipeline  # noqa: E402


# ------------------------------------------------------------------
# Unit tests — transformers
# ------------------------------------------------------------------

class TestCleanRow:
    def test_numeric_coercion(self):
        row = {"quantity": "  5  ", "price": " 12.50 "}
        cleaned = clean_row(row)
        assert cleaned["quantity"] == 5
        assert cleaned["price"] == 12.50

    def test_string_passthrough(self):
        row = {"name": "  Widget A  "}
        cleaned = clean_row(row)
        assert cleaned["name"] == "Widget A"


class TestRunningTotals:
    """These tests validate the running total calculation.

    The critical assertion is that the first row's running_total equals
    the first row's amount — NOT zero.
    """

    def test_single_row(self):
        rows = [{"amount": 50.0}]
        result = calculate_running_totals(rows)
        assert result[0]["running_total"] == 50.0

    def test_multiple_rows(self):
        rows = [
            {"amount": 10.0},
            {"amount": 20.0},
            {"amount": 30.0},
        ]
        result = calculate_running_totals(rows)
        assert result[0]["running_total"] == 10.0
        assert result[1]["running_total"] == 30.0
        assert result[2]["running_total"] == 60.0

    def test_running_total_first_row_is_not_zero(self):
        """Regression test: the first row must include its own amount."""
        rows = [{"amount": 42.0}, {"amount": 8.0}]
        result = calculate_running_totals(rows)
        assert result[0]["running_total"] != 0.0, (
            "First row running_total should not be zero"
        )
        assert result[0]["running_total"] == 42.0


# ------------------------------------------------------------------
# Unit tests — validators
# ------------------------------------------------------------------

class TestValidators:
    def test_validate_row_ok(self):
        row = {"a": 1, "b": 2}
        assert validate_row(row, ["a", "b"]) == []

    def test_validate_row_missing(self):
        row = {"a": 1}
        errors = validate_row(row, ["a", "b"])
        assert len(errors) == 1

    def test_validate_numeric_ok(self):
        val, err = validate_numeric("3.14", "price")
        assert val == pytest.approx(3.14)
        assert err is None

    def test_validate_numeric_bad(self):
        val, err = validate_numeric("abc", "price")
        assert val == 0.0
        assert err is not None


# ------------------------------------------------------------------
# Integration test
# ------------------------------------------------------------------

class TestPipelineIntegration:
    def test_pipeline_output_matches_expected(self, tmp_path):
        """Run the full pipeline and compare to the expected output."""
        task_dir = os.path.join(os.path.dirname(__file__), "..")
        expected_path = os.path.join(task_dir, "data", "expected_output.json")

        with open(expected_path, "r") as fh:
            expected = json.load(fh)

        result = run_pipeline(os.path.join(task_dir, "config.yaml"))

        assert len(result) == len(expected)
        for actual_row, expected_row in zip(result, expected):
            assert actual_row["running_total"] == pytest.approx(
                expected_row["running_total"]
            ), (
                f"Running total mismatch for {actual_row['date']}: "
                f"got {actual_row['running_total']}, "
                f"expected {expected_row['running_total']}"
            )
