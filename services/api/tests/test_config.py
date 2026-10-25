"""Tests for centralized configuration."""

from pathlib import Path

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
