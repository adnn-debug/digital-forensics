"""
Streaming cryptographic multi-hasher for digital evidence integrity.

Computes SHA-256 (forensic baseline), MD5, and SHA-1 (legacy cross-referencing)
concurrently over a single byte stream pass without buffering large payloads into memory.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from app.core.exceptions import StorageException


@dataclass(frozen=True)
class HashDigests:
    """Cryptographic hash digests computed over an evidence byte stream."""

    sha256: str
    md5: str
    sha1: str
    byte_count: int


class MultiHasher:
    """
    Streaming multi-hasher computing SHA-256, MD5, and SHA-1 concurrently.

    Memory bounded: updates in chunks of any size without accumulating full payload.
    """

    def __init__(self) -> None:
        self._sha256 = hashlib.sha256()
        self._md5 = hashlib.md5()
        self._sha1 = hashlib.sha1()
        self._byte_count = 0

    def update(self, chunk: bytes) -> None:
        """Update all digest contexts with a byte chunk."""
        if not chunk:
            return
        self._sha256.update(chunk)
        self._md5.update(chunk)
        self._sha1.update(chunk)
        self._byte_count += len(chunk)

    def finalize(self) -> HashDigests:
        """Produce the finalized hex digests and byte count."""
        return HashDigests(
            sha256=self._sha256.hexdigest().lower(),
            md5=self._md5.hexdigest().lower(),
            sha1=self._sha1.hexdigest().lower(),
            byte_count=self._byte_count,
        )

    @classmethod
    def hash_bytes(cls, data: bytes) -> HashDigests:
        """Compute all digests for an in-memory byte buffer."""
        hasher = cls()
        hasher.update(data)
        return hasher.finalize()

    @classmethod
    def hash_file(cls, path: Path | str, chunk_size: int = 65536) -> HashDigests:
        """Compute all digests for a local file in bounded chunks."""
        hasher = cls()
        file_path = Path(path)
        if not file_path.is_file():
            raise StorageException(message=f"File not found for hashing: {file_path}", path=str(file_path))
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.finalize()

    @classmethod
    async def hash_async_stream(
        cls,
        stream: AsyncIterator[bytes] | BinaryIO | Any,
        initial_chunk: bytes = b"",
        max_size_bytes: int | None = None,
        chunk_size: int = 65536,
    ) -> HashDigests:
        """
        Compute all digests for an asynchronous byte stream with bounded memory.

        Raises StorageException if max_size_bytes is exceeded.
        """
        hasher = cls()
        if initial_chunk:
            if max_size_bytes is not None and len(initial_chunk) > max_size_bytes:
                raise StorageException(
                    message=f"Uploaded file exceeds maximum limit of {max_size_bytes} bytes."
                )
            hasher.update(initial_chunk)

        while True:
            if hasattr(stream, "read"):
                read_fn = stream.read(chunk_size)
                chunk = await read_fn if asyncio.iscoroutine(read_fn) or hasattr(read_fn, "__await__") else read_fn
            elif hasattr(stream, "__anext__"):
                try:
                    chunk = await stream.__anext__()
                except StopAsyncIteration:
                    break
            elif hasattr(stream, "__next__"):
                try:
                    chunk = next(stream)  # type: ignore[arg-type]
                except StopIteration:
                    break
            else:
                break

            if not chunk:
                break

            if max_size_bytes is not None and (hasher._byte_count + len(chunk)) > max_size_bytes:
                raise StorageException(
                    message=f"Uploaded file exceeds maximum limit of {max_size_bytes} bytes."
                )
            hasher.update(chunk)

        return hasher.finalize()
