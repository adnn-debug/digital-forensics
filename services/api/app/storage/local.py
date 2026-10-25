"""Private local filesystem storage adapter implementation."""

import hashlib
import io
import logging
import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from app.core.exceptions import StorageException
from app.storage.base import StorageFileMetadata, StorageProvider
from app.storage.manager import StorageManager

logger = logging.getLogger("ps05.storage.local")


class LocalFilesystemStorageAdapter(StorageProvider):
    """
    Secure private local filesystem storage adapter.

    Enforces path traversal protection, prevents accidental overwrites,
    and isolates evidence bitstreams from public web exposure.
    """

    def __init__(self, manager: StorageManager | None = None) -> None:
        self.manager = manager or StorageManager()
        self.manager.initialize_directories()

    def generate_key(
        self,
        category: str,
        case_id: UUID | str,
        filename: str,
        prefix: str | None = None,
    ) -> str:
        """
        Generate a unique, structured storage key.

        Format: {category}/cases/{clean_case_id}/{unique_prefix}_{clean_filename}
        """
        clean_filename = self.manager.sanitize_filename(filename)
        clean_case_id = str(case_id).strip()
        unique_token = prefix or uuid4().hex[:12]
        key = f"{category}/cases/{clean_case_id}/{unique_token}_{clean_filename}"
        return key

    def _resolve_key_path(self, key: str) -> Path:
        """
        Resolve a storage key into an absolute filesystem path safely.

        Blocks any attempt to navigate outside the vault directory tree.
        """
        if ".." in key or key.startswith("/") or key.startswith("\\"):
            logger.warning("Potential path traversal detected in key: %s", key)
            raise StorageException(
                message="Invalid storage key format. Path traversal vectors are forbidden.",
                path=key,
            )

        parts = Path(key).parts
        if not parts:
            raise StorageException(message="Storage key cannot be empty.")

        category = parts[0]
        relative_remainder = Path(*parts[1:]) if len(parts) > 1 else Path("")

        resolved = self.manager.secure_resolve_path(str(relative_remainder), category=category)
        return resolved

    def write(
        self,
        key: str,
        data: bytes | BinaryIO,
        allow_overwrite: bool = False,
    ) -> StorageFileMetadata:
        """
        Write binary content to the target storage key.

        Writing is atomic: writes to temporary staging first, computes SHA-256,
        and atomically moves into place. Overwrite is blocked by default.
        """
        target_path = self._resolve_key_path(key)

        if target_path.exists() and not allow_overwrite:
            logger.error("Attempted overwrite of existing storage key: %s", key)
            raise StorageException(
                message=f"Storage key '{key}' already exists. Overwriting evidence is forbidden.",
                path=key,
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Stage to temporary scratch area
        staging_filename = f".stage_{uuid4().hex}.tmp"
        staging_path = self.manager.tmp_path / staging_filename

        hasher = hashlib.sha256()
        total_bytes = 0

        try:
            with open(staging_path, "wb") as f_out:
                if isinstance(data, bytes):
                    f_out.write(data)
                    hasher.update(data)
                    total_bytes = len(data)
                elif isinstance(data, io.RawIOBase | io.BufferedIOBase | BinaryIO):
                    while chunk := data.read(65536):
                        f_out.write(chunk)
                        hasher.update(chunk)
                        total_bytes += len(chunk)
                else:
                    raise StorageException(
                        message=f"Unsupported data type for storage write: {type(data)}"
                    )

            # Atomic move from scratch to final vault location
            shutil.move(str(staging_path), str(target_path))
            logger.info("Stored file at key='%s' (%d bytes, sha256=%s)", key, total_bytes, hasher.hexdigest())

        except Exception as exc:
            if staging_path.exists():
                try:
                    staging_path.unlink()
                except OSError:
                    pass
            if not isinstance(exc, StorageException):
                raise StorageException(
                    message=f"Failed to write to storage key '{key}': {exc}",
                    path=key,
                ) from exc
            raise

        return StorageFileMetadata(
            key=key,
            file_size_bytes=total_bytes,
            hash_sha256=hasher.hexdigest(),
            created_at=datetime.now(UTC),
            stored_path_relative=str(target_path.relative_to(self.manager.base_path)),
        )

    def read(self, key: str) -> bytes:
        """Read the raw binary bytes for a storage key."""
        target_path = self._resolve_key_path(key)
        if not target_path.is_file():
            raise StorageException(
                message=f"Requested storage key does not exist: {key}",
                path=key,
            )
        try:
            with open(target_path, "rb") as f_in:
                return f_in.read()
        except OSError as exc:
            raise StorageException(
                message=f"Failed to read storage key '{key}': {exc}",
                path=key,
            ) from exc

    async def read_stream(self, key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """Asynchronously stream chunks of bytes from disk."""
        target_path = self._resolve_key_path(key)
        if not target_path.is_file():
            raise StorageException(
                message=f"Requested storage key does not exist: {key}",
                path=key,
            )
        try:
            with open(target_path, "rb") as f_in:
                while chunk := f_in.read(chunk_size):
                    yield chunk
        except OSError as exc:
            raise StorageException(
                message=f"Streaming error on storage key '{key}': {exc}",
                path=key,
            ) from exc

    def exists(self, key: str) -> bool:
        """Return True if the key points to an existing file."""
        try:
            target_path = self._resolve_key_path(key)
            return target_path.is_file()
        except Exception:
            return False

    def get_size(self, key: str) -> int:
        """Return file size in bytes."""
        target_path = self._resolve_key_path(key)
        if not target_path.is_file():
            raise StorageException(
                message=f"Cannot determine size. Storage key does not exist: {key}",
                path=key,
            )
        try:
            return target_path.stat().st_size
        except OSError as exc:
            raise StorageException(
                message=f"Failed to inspect storage key '{key}': {exc}",
                path=key,
            ) from exc

    def delete(self, key: str) -> bool:
        """
        Controlled deletion of a file at the specified key.

        Clears read-only attributes before deletion if necessary.
        Returns True if deleted, False if file did not exist.
        """
        import stat

        target_path = self._resolve_key_path(key)
        if not target_path.exists():
            return False
        try:
            try:
                target_path.unlink()
            except PermissionError:
                # If read-only flag is set (e.g. S_IREAD on Windows), clear it before unlinking
                target_path.chmod(stat.S_IWRITE | stat.S_IWUSR)
                target_path.unlink()
            logger.info("Deleted file at storage key: %s", key)
            return True
        except OSError as exc:
            raise StorageException(
                message=f"Failed to delete storage key '{key}': {exc}",
                path=key,
            ) from exc

    def get_local_path_readonly(self, key: str) -> Path:
        """Return safe, read-only validated local Path for internal tools."""
        target_path = self._resolve_key_path(key)
        if not target_path.is_file():
            raise StorageException(
                message=f"Storage key does not exist: {key}",
                path=key,
            )
        return target_path

    def lock_readonly(self, key: str) -> Path:
        """Lock file permissions to read-only (0400 on POSIX / S_IREAD on Windows)."""
        import stat

        target_path = self._resolve_key_path(key)
        if not target_path.is_file():
            raise StorageException(
                message=f"Storage key does not exist: {key}",
                path=key,
            )
        try:
            # POSIX 0400 (S_IRUSR) and Windows read-only attribute (S_IREAD)
            target_path.chmod(stat.S_IRUSR | stat.S_IREAD)
            logger.debug("Locked permissions to read-only for storage key: %s", key)
        except OSError as exc:
            logger.warning("Could not set read-only permissions on '%s': %s", key, exc)
        return target_path
