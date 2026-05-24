"""Tests for the user authentication module.

The critical test (test_expired_token_is_rejected) creates a token with an
expiration time in the past and asserts that verify_token raises an error.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
import yaml

# Ensure the task root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from token_manager import create_token, verify_token  # noqa: E402
from auth import register, login, authenticate_request  # noqa: E402
from database import init_db, DB_PATH  # noqa: E402
import database as db_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    """Use a temporary database file for every test."""
    test_db = str(tmp_path / "test_users.db")
    monkeypatch.setattr(db_mod, "DB_PATH", test_db)
    init_db()
    yield
    if os.path.exists(test_db):
        os.unlink(test_db)


# ------------------------------------------------------------------
# Token manager tests
# ------------------------------------------------------------------

class TestTokenManager:
    def test_create_and_verify_token(self):
        """A freshly-created token should be valid."""
        token = create_token(user_id=1, username="alice")
        payload = verify_token(token)
        assert payload["sub"] == 1
        assert payload["username"] == "alice"

    def test_expired_token_is_rejected(self):
        """Tokens whose exp claim is in the past MUST be rejected.

        This is the critical security test that catches the missing
        expiration check.
        """
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        with open(config_path) as fh:
            config = yaml.safe_load(fh)

        # Craft a token that expired 10 seconds ago
        now = datetime.now(timezone.utc)
        payload = {
            "sub": 42,
            "username": "expired_user",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(seconds=10),
        }
        expired_token = pyjwt.encode(
            payload, config["secret_key"], algorithm=config["algorithm"]
        )

        with pytest.raises(pyjwt.ExpiredSignatureError):
            verify_token(expired_token)

    def test_invalid_token_is_rejected(self):
        """A garbage string should not be accepted."""
        with pytest.raises(pyjwt.InvalidTokenError):
            verify_token("not.a.real.token")


# ------------------------------------------------------------------
# Auth workflow tests
# ------------------------------------------------------------------

class TestAuthWorkflow:
    def test_register_creates_user(self):
        user = register("bob", "s3cret")
        assert user.id is not None
        assert user.username == "bob"

    def test_register_duplicate_raises(self):
        register("charlie", "pass1")
        with pytest.raises(ValueError, match="already taken"):
            register("charlie", "pass2")

    def test_login_success(self):
        register("dave", "hunter2")
        result = login("dave", "hunter2")
        assert "token" in result
        assert result["user"]["username"] == "dave"

    def test_login_bad_password(self):
        register("eve", "correct")
        with pytest.raises(ValueError, match="Invalid"):
            login("eve", "wrong")

    def test_login_nonexistent_user(self):
        with pytest.raises(ValueError, match="Invalid"):
            login("nobody", "nope")

    def test_authenticate_request_with_valid_token(self):
        register("frank", "pwd")
        result = login("frank", "pwd")
        claims = authenticate_request(result["token"])
        assert claims["username"] == "frank"
