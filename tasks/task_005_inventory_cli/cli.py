"""Click-based CLI for inventory management."""
from __future__ import annotations

import click
import yaml

from tasks.task_005_inventory_cli.inventory import add_item, remove_item, list_items, search_items, update_quantity


def _load_config() -> dict:
    with open("config.yaml", "r") as fh:
        return yaml.safe_load(fh)


@click.group()
def cli():
    """Inventory management CLI."""
    pass


@cli.command()
@click.argument("name")
@click.option("--quantity", "-q", default=None, type=int, help="Quantity (default from config)")
@click.option("--price", "-p", required=True, type=float, help="Price per unit")
def add(name: str, quantity: int | None, price: float):
    """Add a new item to the inventory."""
    if quantity is None:
        config = _load_config()
        quantity = config.get("default_quantity", 1)
    item = add_item(name, quantity, price)
    click.echo(f"Added item #{item['id']}: {item['name']} (qty: {item['quantity']}, price: {item['price']})")


@cli.command()
@click.argument("item_id", type=int)
def remove(item_id: int):
    """Remove an item by its ID."""
    if remove_item(item_id):
        click.echo(f"Removed item #{item_id}")
    else:
        click.echo(f"Item #{item_id} not found", err=True)


@cli.command("list")
def list_cmd():
    """List all items in the inventory."""
    items = list_items()
    if not items:
        click.echo("Inventory is empty.")
        return
    for item in items:
        click.echo(
            f"  #{item['id']}: {item['name']} — "
            f"qty: {item['quantity']}, price: {item['price']}"
        )


@cli.command()
@click.argument("query")
def search(query: str):
    """Search for items by name (case-insensitive substring match)."""
    results = search_items(query)
    if not results:
        click.echo(f"No items matching '{query}'")
        return
    click.echo(f"Found {len(results)} result(s):")
    for item in results:
        click.echo(
            f"  #{item['id']}: {item['name']} — "
            f"qty: {item['quantity']}, price: {item['price']}"
        )


@cli.command()
@click.argument("item_id", type=int)
@click.argument("new_quantity", type=int)
def update(item_id: int, new_quantity: int):
    """Update the quantity of an item."""
    item = update_quantity(item_id, new_quantity)
    if item:
        click.echo(f"Updated item #{item_id}: qty is now {new_quantity}")
    else:
        click.echo(f"Item #{item_id} not found", err=True)


if __name__ == "__main__":
    cli()
