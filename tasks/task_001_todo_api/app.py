"""Flask TODO API — a small REST API for managing TODO items."""
from __future__ import annotations

from flask import Flask, request, jsonify
from tasks.task_001_todo_api.database import init_db, get_session
from tasks.task_001_todo_api.models import Todo

app = Flask(__name__)


@app.before_request
def _ensure_db():
    """Lazily initialise the database on first request."""
    if not getattr(app, "_db_initialised", False):
        init_db()
        app._db_initialised = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/todos", methods=["GET"])
def list_todos():
    """Return all TODO items."""
    session = get_session()
    todos = session.query(Todo).all()
    return jsonify([t.to_dict() for t in todos]), 200


@app.route("/todos", methods=["POST"])
def create_todo():
    """Create a new TODO item."""
    data = request.get_json(force=True)
    if not data or "title" not in data:
        return jsonify({"error": "title is required"}), 400

    session = get_session()
    todo = Todo(
        title=data["title"],
        description=data.get("description", ""),
        completed=data.get("completed", False),
    )
    session.add(todo)
    session.commit()
    return jsonify(todo.to_dict()), 201


@app.route("/todos/<int:todo_id>", methods=["PUT"])
def update_todo(todo_id: int):
    """Update an existing TODO item.

    BUG: The session.commit() call is missing, so changes are made to the
    in-memory ORM object but never flushed to the database.  After the
    request ends the session is discarded and the update is lost.
    """
    session = get_session()
    todo = session.query(Todo).get(todo_id)
    if todo is None:
        return jsonify({"error": "todo not found"}), 404

    data = request.get_json(force=True)
    if "title" in data:
        todo.title = data["title"]
    if "description" in data:
        todo.description = data["description"]
    if "completed" in data:
        todo.completed = data["completed"]

    # BUG: missing session.commit() — changes are never persisted
    return jsonify(todo.to_dict()), 200


@app.route("/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id: int):
    """Delete a TODO item by its ID."""
    session = get_session()
    todo = session.query(Todo).get(todo_id)
    if todo is None:
        return jsonify({"error": "todo not found"}), 404

    session.delete(todo)
    session.commit()
    return jsonify({"message": "deleted"}), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
