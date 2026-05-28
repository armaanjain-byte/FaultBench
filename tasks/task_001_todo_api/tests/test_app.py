"""Tests for the TODO API — validates that CRUD operations persist correctly."""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

# Ensure the task root is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tasks.task_001_todo_api.app import app  # noqa: E402
from tasks.task_001_todo_api.database import engine, Base, SessionLocal  # noqa: E402


@pytest.fixture(autouse=True)
def _setup_teardown():
    """Create a fresh in-memory database for every test."""
    # Replace engine URL with in-memory SQLite for isolation
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    SessionLocal.remove()


@pytest.fixture()
def client():
    """Provide a Flask test client."""
    app.config["TESTING"] = True
    app._db_initialised = True  # skip lazy init in before_request
    with app.test_client() as c:
        yield c


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_create_todo(client):
    """POST /todos should create a new item and return 201."""
    resp = client.post("/todos", json={"title": "Buy milk"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["title"] == "Buy milk"
    assert body["completed"] is False


def test_list_todos(client):
    """GET /todos should return all items."""
    client.post("/todos", json={"title": "A"})
    client.post("/todos", json={"title": "B"})
    resp = client.get("/todos")
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2


def test_update_todo_persists(client):
    """PUT /todos/<id> must persist the completed flag to the database.

    This is the critical test that catches the missing-commit bug.
    """
    # Create a todo
    create_resp = client.post("/todos", json={"title": "Fix bug"})
    todo_id = create_resp.get_json()["id"]

    # Mark it as completed
    update_resp = client.put(f"/todos/{todo_id}", json={"completed": True})
    assert update_resp.status_code == 200
    assert update_resp.get_json()["completed"] is True

    # Re-fetch and verify persistence
    list_resp = client.get("/todos")
    todos = list_resp.get_json()
    matching = [t for t in todos if t["id"] == todo_id]
    assert len(matching) == 1
    assert matching[0]["completed"] is True, (
        "The completed flag was not persisted to the database"
    )


def test_update_title_persists(client):
    """PUT /todos/<id> must also persist title changes."""
    create_resp = client.post("/todos", json={"title": "Old title"})
    todo_id = create_resp.get_json()["id"]

    client.put(f"/todos/{todo_id}", json={"title": "New title"})

    list_resp = client.get("/todos")
    todos = list_resp.get_json()
    matching = [t for t in todos if t["id"] == todo_id]
    assert matching[0]["title"] == "New title"


def test_delete_todo(client):
    """DELETE /todos/<id> should remove the item."""
    create_resp = client.post("/todos", json={"title": "Temp"})
    todo_id = create_resp.get_json()["id"]

    del_resp = client.delete(f"/todos/{todo_id}")
    assert del_resp.status_code == 200

    list_resp = client.get("/todos")
    assert all(t["id"] != todo_id for t in list_resp.get_json())


def test_update_nonexistent_returns_404(client):
    """PUT /todos/<id> with a bad ID should return 404."""
    resp = client.put("/todos/9999", json={"completed": True})
    assert resp.status_code == 404
