"""User authentication — registration, login, and token verification."""
from __future__ import annotations

import hashlib
import os
from typing import Any

from tasks.task_003_user_auth.models import User
from tasks.task_003_user_auth.database import init_db, insert_user, get_user_by_username
from tasks.task_003_user_auth.token_manager import create_token, verify_token


def _hash_password(password: str, salt: str) -> str:
    """Hash a password with the given salt using SHA-256."""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def register(username: str, password: str) -> User:
    """Register a new user.

    Raises ``ValueError`` if the username is already taken.
    """
    init_db()

    existing = get_user_by_username(username)
    if existing is not None:
        raise ValueError(f"Username '{username}' is already taken")

    salt = os.urandom(16).hex()
    password_hash = _hash_password(password, salt)
    user = User(username=username, password_hash=password_hash, salt=salt)
    return insert_user(user)


def login(username: str, password: str) -> dict[str, Any]:
    """Authenticate a user and return a JWT token.

    Returns ``{"token": "<jwt>", "user": {...}}`` on success.
    Raises ``ValueError`` on bad credentials.
    """
    init_db()

    user = get_user_by_username(username)
    if user is None:
        raise ValueError("Invalid username or password")

    expected_hash = _hash_password(password, user.salt)
    if expected_hash != user.password_hash:
        raise ValueError("Invalid username or password")

    token = create_token(user.id, user.username)
    return {"token": token, "user": user.to_dict()}


def authenticate_request(token: str) -> dict[str, Any]:
    """Verify a JWT token and return the decoded claims.

    Raises ``jwt.InvalidTokenError`` on invalid or expired tokens.
    """
    return verify_token(token)
