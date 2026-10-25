"""Tests for centralized configuration."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_default_paths() -> None:
    """Verify that default settings define expected paths and convert to absolute."""
    settings = Settings()
    assert settings.STORAGE_BASE_PATH.is_absolute()
    assert settings.STORAGE_ORIGINALS_PATH.is_absolute()
    assert settings.STORAGE_ARTIFACTS_PATH.is_absolute()
    assert settings.STORAGE_REPORTS_PATH.is_absolute()
    assert settings.STORAGE_TMP_PATH.is_absolute()
    assert settings.API_V1_STR == "/api/v1"
    assert settings.STORAGE_MAX_UPLOAD_SIZE_BYTES == 5 * 1024 * 1024 * 1024


def test_custom_settings(tmp_path: Path) -> None:
    """Verify overriding settings via kwargs."""
    custom = Settings(
        ENVIRONMENT="testing",
        DEBUG=False,
        STORAGE_BASE_PATH=tmp_path,
        STORAGE_ORIGINALS_PATH=tmp_path / "custom_orig",
    )
    assert custom.ENVIRONMENT == "testing"
    assert custom.DEBUG is False
    assert custom.STORAGE_ORIGINALS_PATH == (tmp_path / "custom_orig").resolve()



def test_production_rejects_debug_mode() -> None:
    """Production-like deployments must never start with debug enabled."""
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=True,
            SECRET_KEY="a" * 64,
            DATABASE_URL="postgresql+asyncpg://user:password@db.internal:5432/ps05",
            REDIS_URL="redis://redis.internal:6379/0",
        )


def test_production_rejects_development_secret() -> None:
    """A long but known development key must not pass production validation."""
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY="ps05-insecure-" + "x" * 64,
            DATABASE_URL="postgresql+asyncpg://user:password@db.internal:5432/ps05",
            REDIS_URL="redis://redis.internal:6379/0",
        )


def test_production_rejects_local_dependencies() -> None:
    """Production config must point to deployed database and Redis services."""
    with pytest.raises(ValidationError, match="localhost"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY="a" * 64,
            DATABASE_URL="postgresql+asyncpg://user:password@db.internal:5432/ps05",
            REDIS_URL="redis://localhost:6379/0",
        )


def test_production_accepts_explicit_safe_configuration() -> None:
    """A production configuration with explicit non-local services and a strong key is accepted."""
    settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        SECRET_KEY="a" * 64,
        DATABASE_URL="postgresql+asyncpg://user:password@db.internal:5432/ps05",
        REDIS_URL="redis://redis.internal:6379/0",
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.DEBUG is False
