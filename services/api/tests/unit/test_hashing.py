"""Unit tests for MultiHasher streaming digests and boundary checks."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from app.core.exceptions import StorageException
from app.storage.hasher import HashDigests, MultiHasher


@pytest.mark.asyncio
async def test_streaming_multi_hasher() -> None:
    """Verify that MultiHasher computes exact SHA-256, MD5, and SHA-1 digests concurrently."""
    payload = b"Digital Forensic Evidence Stream Content 2026 - High Integrity Test"
    hasher = MultiHasher()
    # Update in two separate chunks
    hasher.update(payload[:20])
    hasher.update(payload[20:])
    digests: HashDigests = hasher.finalize()

    assert digests.sha256 == hashlib.sha256(payload).hexdigest().lower()
    assert digests.md5 == hashlib.md5(payload).hexdigest().lower()
    assert digests.sha1 == hashlib.sha1(payload).hexdigest().lower()
    assert digests.byte_count == len(payload)


def test_hasher_hash_bytes() -> None:
    """Verify one-shot memory buffer hashing."""
    data = b"Case-101-Evidence-Payload"
    digests = MultiHasher.hash_bytes(data)

    assert digests.sha256 == hashlib.sha256(data).hexdigest().lower()
    assert digests.md5 == hashlib.md5(data).hexdigest().lower()
    assert digests.sha1 == hashlib.sha1(data).hexdigest().lower()
    assert digests.byte_count == len(data)


def test_hasher_hash_file(tmp_path: Path) -> None:
    """Verify chunked file hashing from disk."""
    sample_file = tmp_path / "test_file.bin"
    content = b"Evidence file stored on filesystem" * 100
    sample_file.write_bytes(content)

    digests = MultiHasher.hash_file(sample_file, chunk_size=32)

    assert digests.sha256 == hashlib.sha256(content).hexdigest().lower()
    assert digests.md5 == hashlib.md5(content).hexdigest().lower()
    assert digests.sha1 == hashlib.sha1(content).hexdigest().lower()
    assert digests.byte_count == len(content)


def test_hasher_nonexistent_file() -> None:
    """Attempting to hash a missing file raises StorageException."""
    with pytest.raises(StorageException):
        MultiHasher.hash_file("nonexistent_path_for_sure.bin")


@pytest.mark.asyncio
async def test_hasher_async_stream() -> None:
    """Verify async generator streaming calculation with initial header chunk."""
    content = b"StreamHeaderBytes" + b"StreamBodyData" * 50
    initial = content[:16]
    body = content[16:]

    async def _async_gen() -> AsyncGenerator[bytes, None]:
        yield body[:50]
        yield body[50:]

    stream_obj = _async_gen()
    digests = await MultiHasher.hash_async_stream(
        stream=stream_obj,
        initial_chunk=initial,
        chunk_size=32,
    )

    assert digests.sha256 == hashlib.sha256(content).hexdigest().lower()
    assert digests.md5 == hashlib.md5(content).hexdigest().lower()
    assert digests.sha1 == hashlib.sha1(content).hexdigest().lower()
    assert digests.byte_count == len(content)


@pytest.mark.asyncio
async def test_hasher_async_stream_max_size_exceeded() -> None:
    """Stream exceeding max_size_bytes raises StorageException immediately."""
    initial = b"12345"

    async def _async_gen() -> AsyncGenerator[bytes, None]:
        yield b"67890"
        yield b"overflow"

    with pytest.raises(StorageException) as exc_info:
        await MultiHasher.hash_async_stream(
            stream=_async_gen(),
            initial_chunk=initial,
            max_size_bytes=8,
        )
    assert "exceeds maximum limit" in str(exc_info.value)
