"""Tests for the inventory CLI and search functionality.

The critical tests verify that search uses case-insensitive substring matching.
"""
from __future__ import annotations

import json
import os
import sys

import pytest
from click.testing import CliRunner

# Ensure the task root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tasks.task_005_inventory_cli.inventory import add_item, remove_item, list_items, search_items, update_quantity  # noqa: E402
from tasks.task_005_inventory_cli.cli import cli  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_inventory(tmp_path):
    """Use a temporary JSON file for every test."""
    storage = str(tmp_path / "test_inventory.json")
    # Monkey-patch at module level so the CLI also picks it up
    import tasks.task_005_inventory_cli.inventory as inv_mod
    import tasks.task_005_inventory_cli.storage as sto_mod

    original_get = sto_mod._get_storage_path

    def _test_path():
        return storage

    sto_mod._get_storage_path = _test_path
    yield
    sto_mod._get_storage_path = original_get


# ------------------------------------------------------------------
# Inventory logic tests
# ------------------------------------------------------------------

class TestInventoryLogic:
    def test_add_item(self):
        item = add_item("Widget A", 10, 5.00)
        assert item["name"] == "Widget A"
        assert item["quantity"] == 10
        assert item["id"] == 1

    def test_add_multiple_items(self):
        add_item("A", 1, 1.0)
        item2 = add_item("B", 2, 2.0)
        assert item2["id"] == 2

    def test_remove_item(self):
        item = add_item("Remove Me", 1, 1.0)
        assert remove_item(item["id"]) is True
        assert list_items() == []

    def test_remove_nonexistent(self):
        assert remove_item(9999) is False

    def test_list_items(self):
        add_item("X", 1, 1.0)
        add_item("Y", 2, 2.0)
        items = list_items()
        assert len(items) == 2

    def test_update_quantity(self):
        item = add_item("Z", 5, 10.0)
        updated = update_quantity(item["id"], 20)
        assert updated is not None
        assert updated["quantity"] == 20

    def test_update_nonexistent(self):
        assert update_quantity(9999, 1) is None


# ------------------------------------------------------------------
# Search tests — these catch the exact-match bug
# ------------------------------------------------------------------

class TestSearchItems:
    """Validate that search uses case-insensitive substring matching."""

    def test_search_exact_name(self):
        """Exact name should always match."""
        add_item("Widget A", 10, 5.00)
        results = search_items("Widget A")
        assert len(results) == 1

    def test_search_substring(self):
        """A substring of the name should match.

        This is the critical test that catches the exact-match bug.
        """
        add_item("Widget A", 10, 5.00)
        add_item("Widget B", 5, 12.50)
        add_item("Gadget C", 3, 20.00)

        results = search_items("Widget")
        assert len(results) == 2, (
            f"Expected 2 results for 'Widget', got {len(results)} — "
            "search may be using exact match instead of substring"
        )

    def test_search_case_insensitive(self):
        """Search must be case-insensitive."""
        add_item("Widget A", 10, 5.00)

        results = search_items("widget a")
        assert len(results) == 1, (
            "Case-insensitive search for 'widget a' should match 'Widget A'"
        )

    def test_search_partial_case_insensitive(self):
        """Partial query in different case should match."""
        add_item("Widget A", 10, 5.00)
        add_item("Widget B", 5, 12.50)

        results = search_items("wid")
        assert len(results) == 2, (
            "Searching for 'wid' should match 'Widget A' and 'Widget B'"
        )

    def test_search_no_results(self):
        """A query that matches nothing should return an empty list."""
        add_item("Widget A", 10, 5.00)
        results = search_items("nonexistent")
        assert len(results) == 0


# ------------------------------------------------------------------
# CLI integration tests
# ------------------------------------------------------------------

class TestCLI:
    def test_cli_add_and_list(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["add", "Test Item", "-p", "9.99", "-q", "3"])
        assert result.exit_code == 0
        assert "Added" in result.output

        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "Test Item" in result.output

    def test_cli_search(self):
        runner = CliRunner()
        runner.invoke(cli, ["add", "Alpha Widget", "-p", "5.00"])
        runner.invoke(cli, ["add", "Beta Widget", "-p", "10.00"])
        runner.invoke(cli, ["add", "Gamma Gadget", "-p", "15.00"])

        result = runner.invoke(cli, ["search", "Widget"])
        assert result.exit_code == 0
        assert "2 result" in result.output

    def test_cli_remove(self):
        runner = CliRunner()
        runner.invoke(cli, ["add", "To Remove", "-p", "1.00"])
        result = runner.invoke(cli, ["remove", "1"])
        assert result.exit_code == 0
        assert "Removed" in result.output
