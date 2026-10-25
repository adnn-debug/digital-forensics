"""Storage provider abstract base class and data transfer objects."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID


@dataclass(frozen=True)
class StorageFileMetadata:
    """Metadata for a securely stored binary artifact."""

    key: str
    file_size_bytes: int
    hash_sha256: str
    stored_path_relative: str
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )



class StorageProvider(ABC):
    """Abstract interface defining private evidence vault operations."""

    @abstractmethod
    def generate_key(
        self,
        category: str,
        case_id: UUID | str,
        filename: str,
        prefix: str | None = None,
    ) -> str:
        """Generate a cryptographically unique storage key."""
        pass

    @abstractmethod
    def write(
        self,
        key: str,
        data: bytes | BinaryIO,
        allow_overwrite: bool = False,
    ) -> StorageFileMetadata:
        """Write binary data to storage key without overwrite unless explicitly allowed."""
        pass

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Read complete file content for a storage key."""
        pass

    @abstractmethod
    def read_stream(self, key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """Stream file bytes asynchronously."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check whether a file exists for the given storage key."""
        pass

    @abstractmethod
    def get_size(self, key: str) -> int:
        """Retrieve file size in bytes for a storage key."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Controlled deletion of a stored artifact."""
        pass

    @abstractmethod
    def get_local_path_readonly(self, key: str) -> Path:
        """Provide a secure local path for internal tools requiring file handles."""
        pass

    @abstractmethod
    def lock_readonly(self, key: str) -> Path:
        """Lock file permissions to read-only (0400 on POSIX, S_IREAD on Windows)."""
        pass
