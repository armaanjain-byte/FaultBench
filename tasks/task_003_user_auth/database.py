"""SQLite-backed user storage."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from models import User


DB_PATH = "users.db"


def _get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the users table if it does not exist."""
    conn = _get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def insert_user(user: User) -> User:
    """Insert a new user and return it with the generated id."""
    conn = _get_connection()
    cursor = conn.execute(
        "INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
        (user.username, user.password_hash, user.salt, user.created_at.isoformat()),
    )
    user.id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user


def get_user_by_username(username: str) -> User | None:
    """Look up a user by username.  Returns None if not found."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT id, username, password_hash, salt, created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        salt=row["salt"],
    )


def get_user_by_id(user_id: int) -> User | None:
    """Look up a user by numeric id."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT id, username, password_hash, salt, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        salt=row["salt"],
    )
