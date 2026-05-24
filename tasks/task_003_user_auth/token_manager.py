"""JWT token creation and verification.

BUG: verify_token does NOT validate the token's expiration claim ('exp').
Expired tokens are accepted as valid, which is a security vulnerability.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import yaml


def _load_config() -> dict[str, Any]:
    with open("config.yaml", "r") as fh:
        return yaml.safe_load(fh)


def create_token(user_id: int, username: str) -> str:
    """Create a signed JWT for the given user.

    The token includes an ``exp`` claim set to ``now + token_expiry_seconds``
    from config.
    """
    config = _load_config()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "iat": now,
        "exp": now + timedelta(seconds=config["token_expiry_seconds"]),
    }
    return jwt.encode(payload, config["secret_key"], algorithm=config["algorithm"])


def verify_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT token.

    BUG: The ``options`` dict disables expiration verification, so expired
    tokens are silently accepted.  The fix is to remove the
    ``"verify_exp": False`` option (or set it to True).

    Returns the decoded payload dict on success.
    Raises ``jwt.InvalidTokenError`` (or subclass) on failure.
    """
    config = _load_config()
    payload = jwt.decode(
        token,
        config["secret_key"],
        algorithms=[config["algorithm"]],
        options={"verify_exp": False},  # BUG: expiration not checked
    )
    return payload
