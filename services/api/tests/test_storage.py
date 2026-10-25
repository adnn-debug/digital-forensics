"""Tests for StorageManager and path traversal mitigations."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.exceptions import SecurityViolationException
from app.storage.manager import StorageManager


def test_storage_initialization(tmp_path: Path) -> None:
    """Verify that StorageManager creates all required directories."""
    settings = Settings(
        STORAGE_BASE_PATH=tmp_path,
        STORAGE_ORIGINALS_PATH=tmp_path / "orig",
        STORAGE_ARTIFACTS_PATH=tmp_path / "art",
        STORAGE_REPORTS_PATH=tmp_path / "rep",
        STORAGE_TMP_PATH=tmp_path / "tmp",
    )
    mgr = StorageManager(settings=settings)
    mgr.initialize_directories()

    assert (tmp_path / "orig").is_dir()
    assert (tmp_path / "art").is_dir()
    assert (tmp_path / "rep").is_dir()
    assert (tmp_path / "tmp").is_dir()

    health = mgr.check_storage_health()
    assert health["status"] == "HEALTHY"


def test_secure_resolve_path_success(tmp_path: Path) -> None:
    """Verify safe path resolution within the vault."""
    settings = Settings(
        STORAGE_BASE_PATH=tmp_path,
        STORAGE_ORIGINALS_PATH=tmp_path / "orig",
    )
    mgr = StorageManager(settings=settings)
    mgr.initialize_directories()

    resolved = mgr.secure_resolve_path("case_123/evidence_456.jpg", category="originals")
    assert resolved == (tmp_path / "orig" / "case_123" / "evidence_456.jpg").resolve()


def test_path_traversal_detection(tmp_path: Path) -> None:
    """Verify that path traversal attempts raise SecurityViolationException."""
    settings = Settings(
        STORAGE_BASE_PATH=tmp_path,
        STORAGE_ORIGINALS_PATH=tmp_path / "orig",
    )
    mgr = StorageManager(settings=settings)
    mgr.initialize_directories()

    with pytest.raises(SecurityViolationException) as exc_info:
        mgr.secure_resolve_path("../../etc/shadow", category="originals")
    assert "Path traversal attempt blocked" in str(exc_info.value)


def test_filename_sanitization() -> None:
    """Verify illegal characters and directory separators are stripped."""
    assert StorageManager.sanitize_filename("valid_image.png") == "valid_image.png"
    assert StorageManager.sanitize_filename("../../etc/passwd.jpg") == "etcpasswd.jpg"
    assert StorageManager.sanitize_filename("bad<char>:name|file?.mp4") == "badcharnamefile.mp4"
