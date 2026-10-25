"""Dependency injection providers for database, redis, storage, and authentication."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.models.user import User
from app.db.session import get_db_session
from app.storage.manager import StorageManager

if TYPE_CHECKING:
    from app.storage.local import LocalFilesystemStorageAdapter

logger = logging.getLogger("ps05.deps")

_storage_manager: StorageManager | None = None
_storage_adapter: Any | None = None  # LocalFilesystemStorageAdapter, imported lazily
_redis_pool: aioredis.ConnectionPool[Any] | None = None

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def get_storage() -> StorageManager:
    """Provide singleton StorageManager instance."""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager()
        _storage_manager.initialize_directories()
    return _storage_manager


def get_storage_adapter() -> LocalFilesystemStorageAdapter:
    """Provide singleton LocalFilesystemStorageAdapter instance."""
    global _storage_adapter
    if _storage_adapter is None:
        from app.storage.local import LocalFilesystemStorageAdapter

        _storage_adapter = LocalFilesystemStorageAdapter(manager=get_storage())
    return _storage_adapter


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide scoped async database session."""
    async for session in get_db_session():
        yield session


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------


def get_redis_pool() -> aioredis.ConnectionPool[Any]:
    """Return shared Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            max_connections=20,
        )
    return _redis_pool


async def get_redis_client() -> AsyncGenerator[aioredis.Redis[Any], None]:
    """Provide an async Redis client."""
    client = aioredis.Redis(connection_pool=get_redis_pool())
    try:
        yield client
    finally:
        await client.close()


async def check_redis_connectivity() -> dict[str, Any]:
    """Ping Redis to test connectivity and measure latency."""
    start_time = time.perf_counter()
    try:
        client = aioredis.Redis(connection_pool=get_redis_pool())
        pong = await client.ping()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        await client.close()
        if pong:
            return {"status": "HEALTHY", "latency_ms": latency_ms}
        return {"status": "UNHEALTHY", "error": "Invalid PING response", "latency_ms": latency_ms}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning("Redis connectivity check failed: %s", exc)
        return {"status": "UNHEALTHY", "error": str(exc), "latency_ms": latency_ms}


# ---------------------------------------------------------------------------
# Authentication & authorisation
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "UNAUTHENTICATED", "message": "Invalid or missing authentication credentials."},
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Validate Bearer JWT and return the active User ORM row.

    Raises HTTP 401 for missing/invalid/expired tokens.
    Raises HTTP 403 for inactive accounts.
    """
    from sqlalchemy import select

    if credentials is None:
        raise _CREDENTIALS_EXCEPTION

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id_str: str | None = payload.get("sub")
        if not user_id_str:
            raise _CREDENTIALS_EXCEPTION
    except JWTError:
        raise _CREDENTIALS_EXCEPTION from None

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise _CREDENTIALS_EXCEPTION from None

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None:
        raise _CREDENTIALS_EXCEPTION
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_INACTIVE", "message": "This account has been deactivated."},
        )

    return user


async def get_current_user_flexible(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str | None = None,
) -> User:
    """
    Validate JWT from either Authorization header or ?token= query parameter.
    Enables authenticated media streaming (e.g., img tags in HTML).
    """
    raw_token = credentials.credentials if credentials is not None else token
    if not raw_token:
        raise _CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(raw_token)
        user_id_str: str | None = payload.get("sub")
        if not user_id_str:
            raise _CREDENTIALS_EXCEPTION
    except JWTError:
        raise _CREDENTIALS_EXCEPTION from None

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise _CREDENTIALS_EXCEPTION from None

    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None:
        raise _CREDENTIALS_EXCEPTION
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ACCOUNT_INACTIVE", "message": "This account has been deactivated."},
        )

    return user


# Type alias for route dependency
CurrentUser = Annotated[User, Depends(get_current_user)]
FlexibleUser = Annotated[User, Depends(get_current_user_flexible)]


def require_roles(*allowed_roles: str) -> Any:
    """
    Factory that returns a FastAPI dependency enforcing role-based access.

    Usage::

        @router.get("/admin-only")
        async def admin_route(user = Depends(require_roles("ADMIN"))):
            ...
    """

    async def _check(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_PERMISSIONS",
                    "message": f"Role '{user.role}' is not authorized for this action.",
                    "required_roles": list(allowed_roles),
                },
            )
        return user

    return Depends(_check)
