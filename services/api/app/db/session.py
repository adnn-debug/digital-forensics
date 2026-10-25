"""Async SQLAlchemy engine, session management, and connectivity verification."""

import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger("ps05.db")

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Initialize or return the cached async SQLAlchemy engine."""
    global _engine, _session_maker
    if _engine is None:
        settings = get_settings()
        url = settings.DATABASE_URL

        # Engine configuration tailored for forensic reliability
        engine_kwargs: dict[str, Any] = {
            "echo": False,
            "future": True,
        }

        # Configure connection pooling appropriately
        if url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_recycle"] = 1800

        _engine = create_async_engine(url, **engine_kwargs)
        _session_maker = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.info("Initialized database engine for %s", url.split("@")[-1] if "@" in url else url)

    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory."""
    if _session_maker is None:
        get_engine()
    assert _session_maker is not None
    return _session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an isolated async database session."""
    session_factory = get_session_maker()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connectivity() -> dict[str, Any]:
    """Execute 'SELECT 1' to verify database availability and latency."""
    engine = get_engine()
    start_time = time.perf_counter()
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if val == 1:
                return {
                    "status": "HEALTHY",
                    "latency_ms": latency_ms,
                    "database": str(engine.url).split("://")[0],
                }
            return {
                "status": "UNHEALTHY",
                "error": "Unexpected return value",
                "latency_ms": latency_ms,
            }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error("Database connectivity check failed: %s", exc)
        return {
            "status": "UNHEALTHY",
            "error": str(exc),
            "latency_ms": latency_ms,
        }


async def close_db_engine() -> None:
    """Gracefully dispose database connection pools upon application shutdown."""
    global _engine, _session_maker
    if _engine is not None:
        logger.info("Disposing database engine pools...")
        await _engine.dispose()
        _engine = None
        _session_maker = None
