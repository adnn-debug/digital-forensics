"""Synchronous Redis connection manager for RQ task queue."""

from __future__ import annotations

import logging
from typing import Any

import redis

from app.core.config import get_settings

logger = logging.getLogger("ps05.queue.connection")

_sync_redis_client: redis.Redis[Any] | None = None


def get_redis_sync_client(url: str | None = None) -> redis.Redis[Any]:
    """
    Return or create singleton synchronous Redis client for RQ.
    Supports injecting custom URL or using application settings.
    """
    global _sync_redis_client
    if url is not None:
        return redis.Redis.from_url(url)

    if _sync_redis_client is None:
        settings = get_settings()
        logger.info("Connecting synchronous Redis client to %s", settings.REDIS_URL)
        _sync_redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
    return _sync_redis_client


def set_redis_sync_client(client: redis.Redis[Any] | None) -> None:
    """Inject a test or mock Redis client (e.g. fakeredis.FakeRedis)."""
    global _sync_redis_client
    _sync_redis_client = client
