"""Pytest fixtures for API and database integration tests."""

import os
from collections.abc import AsyncGenerator
from typing import Any

import fakeredis.aioredis as fake_aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set testing environment variables before importing app
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"

from app.api import deps
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.main import app
from app.storage.manager import StorageManager


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Fixture providing isolated settings pointing to a temporary storage directory."""
    test_storage = tmp_path_factory.mktemp("forensic_test_storage")
    settings = Settings(
        ENVIRONMENT="testing",
        DEBUG=False,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://localhost:6379/15",
        STORAGE_BASE_PATH=test_storage,
        STORAGE_ORIGINALS_PATH=test_storage / "originals",
        STORAGE_ARTIFACTS_PATH=test_storage / "artifacts",
        STORAGE_REPORTS_PATH=test_storage / "reports",
        STORAGE_TMP_PATH=test_storage / "tmp",
    )
    return settings


@pytest.fixture(autouse=True)
def override_settings(test_settings: Settings) -> None:
    """Override get_settings dependency for all tests."""
    app.dependency_overrides[get_settings] = lambda: test_settings


@pytest.fixture
def test_storage(test_settings: Settings) -> StorageManager:
    """Fixture providing an initialized test storage manager."""
    mgr = StorageManager(settings=test_settings)
    mgr.initialize_directories()
    app.dependency_overrides[deps.get_storage] = lambda: mgr
    deps._storage_manager = mgr
    return mgr


@pytest.fixture
def test_storage_adapter(test_storage: StorageManager) -> Any:
    """Fixture providing a LocalFilesystemStorageAdapter bound to isolated test vaults."""
    from app.storage.local import LocalFilesystemStorageAdapter

    adapter = LocalFilesystemStorageAdapter(manager=test_storage)
    app.dependency_overrides[deps.get_storage_adapter] = lambda: adapter
    deps._storage_adapter = adapter
    return adapter


@pytest.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """In-memory async SQLite engine with FK enforcement for fast, isolated test execution."""
    from sqlalchemy import event
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign key enforcement for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn: Any, _connection_record: Any) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from app.db.triggers import install_security_triggers

        await install_security_triggers(conn)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    import app.db.session as session_module
    old_session_maker = session_module._session_maker
    session_module._session_maker = session_factory

    async with session_factory() as session:
        # Wire the session into the FastAPI app's dependency overrides
        # so that auth and case endpoints operate on the same in-memory DB
        async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
            yield session

        app.dependency_overrides[deps.get_db] = _override_get_db
        yield session
        app.dependency_overrides.pop(deps.get_db, None)

    session_module._session_maker = old_session_maker
    await engine.dispose()


@pytest.fixture
def fake_redis() -> Any:
    """In-memory fake Redis client for reliable testing without external Redis service."""
    server = fake_aioredis.FakeServer()  # type: ignore[attr-defined]
    client = fake_aioredis.FakeRedis(server=server)
    return client


@pytest.fixture
def fake_sync_redis() -> Any:
    """Synchronous fake Redis client for RQ task queue testing."""
    import fakeredis

    from app.queue.connection import set_redis_sync_client

    client = fakeredis.FakeRedis()
    set_redis_sync_client(client)
    yield client
    set_redis_sync_client(None)



@pytest.fixture
async def async_client(test_storage: StorageManager, test_db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX AsyncClient configured with ASGI transport and the in-memory DB session."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
