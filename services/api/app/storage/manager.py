"""Private local storage manager and security validator."""

import logging
import os
import re
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.core.exceptions import SecurityViolationException, StorageException

logger = logging.getLogger("ps05.storage")


class StorageManager:
    """Manages private local evidence vaults and directory sandboxes."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_path = self.settings.STORAGE_BASE_PATH
        self.originals_path = self.settings.STORAGE_ORIGINALS_PATH
        self.artifacts_path = self.settings.STORAGE_ARTIFACTS_PATH
        self.reports_path = self.settings.STORAGE_REPORTS_PATH
        self.tmp_path = self.settings.STORAGE_TMP_PATH

    def initialize_directories(self) -> None:
        """Create all required private storage directories if they do not exist."""
        directories = [
            self.base_path,
            self.originals_path,
            self.artifacts_path,
            self.reports_path,
            self.tmp_path,
        ]
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                logger.debug("Verified storage directory: %s", directory)
            except Exception as exc:
                raise StorageException(
                    message=f"Failed to initialize storage directory: {directory}",
                    path=str(directory),
                ) from exc
        logger.info("All private storage vaults initialized successfully.")

    def secure_resolve_path(self, relative_path: str, category: str = "originals") -> Path:
        """
        Safely resolve a relative path within the specified vault category.

        Guarantees that path traversal attempts (e.g. '../../etc/shadow') are blocked.
        """
        category_map = {
            "originals": self.originals_path,
            "artifacts": self.artifacts_path,
            "reports": self.reports_path,
            "tmp": self.tmp_path,
        }
        root_dir = category_map.get(category, self.base_path)

        # Sanitize any malicious components
        sanitized_rel = Path(relative_path)
        resolved_target = (root_dir / sanitized_rel).resolve()

        # Strict containment check
        if not resolved_target.is_relative_to(root_dir.resolve()):
            logger.warning(
                "Security Alert: Path traversal attempt blocked! root='%s' target='%s'",
                root_dir,
                resolved_target,
            )
            raise SecurityViolationException(
                message="Path traversal attempt blocked. Access outside vault root is forbidden.",
                vector="PATH_TRAVERSAL",
            )

        return resolved_target

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Strip illegal filesystem characters and path separators."""
        cleaned = re.sub(r'[\\/*?:"<>|]', "", filename)
        cleaned = cleaned.replace("..", "")
        cleaned = cleaned.strip(" .")
        return cleaned or "unnamed_evidence"

    def check_storage_health(self) -> dict[str, Any]:
        """Verify that all storage directories are accessible and writable."""
        categories = {
            "originals": self.originals_path,
            "artifacts": self.artifacts_path,
            "reports": self.reports_path,
            "tmp": self.tmp_path,
        }
        health_status: dict[str, Any] = {}
        all_healthy = True

        for name, path in categories.items():
            try:
                if not path.exists():
                    path.mkdir(parents=True, exist_ok=True)
                test_file = path / f".health_check_{os.getpid()}.tmp"
                test_file.write_text("health_check")
                test_file.unlink()
                health_status[name] = {"status": "HEALTHY", "path": str(path)}
            except Exception as exc:
                all_healthy = False
                health_status[name] = {
                    "status": "UNHEALTHY",
                    "error": str(exc),
                    "path": str(path),
                }

        return {
            "status": "HEALTHY" if all_healthy else "UNHEALTHY",
            "directories": health_status,
        }
