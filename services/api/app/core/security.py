"""Password hashing and JWT token utilities for PS-05 authentication."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import bcrypt
from jose import jwt  # type: ignore[import-untyped]

from app.core.config import get_settings

logger = logging.getLogger("ps05.security")

# Token configuration
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1-hour session
ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Password helpers (bcrypt 5.x native API)
# ---------------------------------------------------------------------------


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash of the supplied plaintext password."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True if *plaintext* matches *hashed*, using constant-time comparison."""
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(
    subject: str | UUID,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Issue a signed JWT containing the user ID and role.

    The token is signed with HS256 using the application SECRET_KEY.
    It expires after ACCESS_TOKEN_EXPIRE_MINUTES and carries a ``sub``
    (subject), ``role``, and ``iat`` (issued-at) claim.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)

    return str(jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM))


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.  Raises ``jose.JWTError`` on failure.

    The caller is expected to catch JWTError and translate it to an
    HTTP 401 response — see ``app.api.deps.get_current_user``.
    """
    settings = get_settings()
    return cast(dict[str, Any], jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM]))


# ---------------------------------------------------------------------------
# Audit hash helpers
# ---------------------------------------------------------------------------


def compute_event_hash(
    event_type: str,
    action_description: str,
    user_id: str | None,
    case_id: str | None,
    previous_hash: str | None,
    timestamp: str,
) -> str:
    """
    Compute a deterministic SHA-256 chain hash for an audit event.

    Incorporates the previous event hash so each event is
    cryptographically chained to its predecessor.
    """
    chain_input = "|".join(
        [
            event_type,
            action_description,
            user_id or "",
            case_id or "",
            previous_hash or "GENESIS",
            timestamp,
        ]
    )
    return hashlib.sha256(chain_input.encode()).hexdigest()


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "compute_event_hash",
    "ACCESS_TOKEN_EXPIRE_MINUTES",
]
