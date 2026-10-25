"""Focused regression tests for security controls added during hardening."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import deps
from app.api.v1 import auth
from app.core.security import create_access_token, decode_access_token


def _request() -> Request:
    """Create a minimal Starlette request with a direct client IP."""
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "headers": [],
            "client": ("192.0.2.10", 12345),
            "server": ("testserver", 80),
        }
    )


def test_access_tokens_include_unique_jti() -> None:
    """Each new token needs a distinct ID so logout can revoke only that session."""
    first = create_access_token(subject="00000000-0000-0000-0000-000000000001", role="EXAMINER")
    second = create_access_token(subject="00000000-0000-0000-0000-000000000001", role="EXAMINER")

    assert decode_access_token(first)["jti"]
    assert decode_access_token(first)["jti"] != decode_access_token(second)["jti"]


@pytest.mark.asyncio
async def test_revoked_token_id_is_rejected() -> None:
    """A revoked JTI must be translated into an authentication failure."""
    client = SimpleNamespace(
        exists=AsyncMock(return_value=1),
        close=AsyncMock(),
    )
    with (
        patch("app.api.deps.get_settings", return_value=SimpleNamespace(ENVIRONMENT="production")),
        patch("app.api.deps.get_redis_pool", return_value=object()),
        patch("app.api.deps.aioredis.Redis", return_value=client),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await deps._ensure_token_not_revoked({"jti": "revoked-session-id"})

    assert exc_info.value.status_code == 401
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_rate_limit_rejects_excessive_account_attempts() -> None:
    """More than ten attempts for one account in the window must be throttled."""
    client = SimpleNamespace(
        incr=AsyncMock(side_effect=[1, 11]),
        expire=AsyncMock(),
        close=AsyncMock(),
    )
    with (
        patch("app.api.v1.auth.get_settings", return_value=SimpleNamespace(ENVIRONMENT="production")),
        patch("app.api.v1.auth.get_redis_pool", return_value=object()),
        patch("app.api.v1.auth.aioredis.Redis", return_value=client),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await auth._enforce_login_rate_limit(_request(), "person@example.test")

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "900"
    client.close.assert_awaited_once()
