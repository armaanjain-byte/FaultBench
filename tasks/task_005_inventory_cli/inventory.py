"""Core inventory management logic.

BUG: search_items uses exact equality (==) instead of case-insensitive
substring matching.  Searching for 'wid' will NOT match 'Widget A'.
"""
from __future__ import annotations

from typing import Any

from storage import load_inventory, save_inventory, next_id


def add_item(
    name: str,
    quantity: int,
    price: float,
    storage_path: str | None = None,
) -> dict[str, Any]:
    """Add a new item to the inventory.

    Returns the newly created item dict (with generated id).
    """
    items = load_inventory(storage_path)
    new_item: dict[str, Any] = {
        "id": next_id(items),
        "name": name,
        "quantity": quantity,
        "price": price,
    }
    items.append(new_item)
    save_inventory(items, storage_path)
    return new_item


def remove_item(item_id: int, storage_path: str | None = None) -> bool:
    """Remove an item by its ID.

    Returns True if the item was found and removed, False otherwise.
    """
    items = load_inventory(storage_path)
    original_len = len(items)
    items = [i for i in items if i.get("id") != item_id]
    if len(items) == original_len:
        return False
    save_inventory(items, storage_path)
    return True


def list_items(storage_path: str | None = None) -> list[dict[str, Any]]:
    """Return all items in the inventory."""
    return load_inventory(storage_path)


def search_items(
    query: str,
    storage_path: str | None = None,
) -> list[dict[str, Any]]:
    """Search for items whose name matches the query.

    The specification requires **case-insensitive substring matching**:
    searching for ``'wid'`` should match ``'Widget A'``.

    BUG: Uses exact equality (``==``) instead of case-insensitive
    substring containment.
    """
    items = load_inventory(storage_path)
    results: list[dict[str, Any]] = []
    for item in items:
        # BUG: exact match instead of case-insensitive substring
        if item.get("name") == query:
            results.append(item)
    return results


def update_quantity(
    item_id: int,
    new_quantity: int,
    storage_path: str | None = None,
) -> dict[str, Any] | None:
    """Update the quantity of an item by ID.

    Returns the updated item, or None if the item was not found.
    """
    items = load_inventory(storage_path)
    for item in items:
        if item.get("id") == item_id:
            item["quantity"] = new_quantity
            save_inventory(items, storage_path)
            return item
    return None
