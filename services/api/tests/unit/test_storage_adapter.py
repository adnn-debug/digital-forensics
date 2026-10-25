"""Unit tests for LocalFilesystemStorageAdapter and transaction safety."""

import hashlib
import io

import pytest

from app.core.exceptions import StorageException
from app.storage.local import LocalFilesystemStorageAdapter
from app.storage.transaction import (
    StagedStorageTransaction,
    cleanup_temporary_files,
)


def test_write_and_read_binary_data(test_storage_adapter: LocalFilesystemStorageAdapter) -> None:
    """Verify write, hash calculation, and read retrieval of stored evidence."""
    payload = b"Digital Forensics Bitstream Evidence Sample 2026"
    expected_hash = hashlib.sha256(payload).hexdigest()

    key = test_storage_adapter.generate_key(
        category="originals",
        case_id="CAS-TEST-01",
        filename="evidence.raw",
    )

    metadata = test_storage_adapter.write(key=key, data=payload)

    assert metadata.key == key
    assert metadata.file_size_bytes == len(payload)
    assert metadata.hash_sha256 == expected_hash

    # Read back and verify byte exactness
    read_bytes = test_storage_adapter.read(key)
    assert read_bytes == payload
    assert test_storage_adapter.exists(key) is True
    assert test_storage_adapter.get_size(key) == len(payload)


def test_write_from_binary_stream(test_storage_adapter: LocalFilesystemStorageAdapter) -> None:
    """Verify writing data from a stream/file-like object."""
    payload = b"Streamed Video Packet Bitstream Chunk"
    stream = io.BytesIO(payload)

    key = test_storage_adapter.generate_key(
        category="originals",
        case_id="CAS-STREAM-01",
        filename="stream.mp4",
    )

    metadata = test_storage_adapter.write(key=key, data=stream)
    assert metadata.file_size_bytes == len(payload)
    assert test_storage_adapter.read(key) == payload


def test_write_duplicate_key_without_overwrite_raises(
    test_storage_adapter: LocalFilesystemStorageAdapter,
) -> None:
    """Verify that writing to an existing key without allow_overwrite raises an error."""
    key = "originals/cases/CAS-DUP/duplicate_evidence.jpg"
    payload1 = b"Original Content"
    payload2 = b"Tampered Content"

    test_storage_adapter.write(key=key, data=payload1)

    with pytest.raises(StorageException) as exc_info:
        test_storage_adapter.write(key=key, data=payload2, allow_overwrite=False)

    assert "already exists" in str(exc_info.value).lower()
    # Verify original remains unaltered
    assert test_storage_adapter.read(key) == payload1


def test_write_duplicate_key_with_allow_overwrite(
    test_storage_adapter: LocalFilesystemStorageAdapter,
) -> None:
    """Verify that allow_overwrite=True succeeds when explicitly permitted."""
    key = "tmp/cases/CAS-OVERWRITE/temp_working.tmp"
    test_storage_adapter.write(key=key, data=b"Version 1")
    test_storage_adapter.write(key=key, data=b"Version 2 Updated", allow_overwrite=True)

    assert test_storage_adapter.read(key) == b"Version 2 Updated"


@pytest.mark.asyncio
async def test_read_stream_chunks(test_storage_adapter: LocalFilesystemStorageAdapter) -> None:
    """Verify async chunked streaming read."""
    payload = b"ChunkA" * 1000 + b"ChunkB" * 1000
    key = "artifacts/cases/CAS-STREAM/large_artifact.bin"
    test_storage_adapter.write(key=key, data=payload)

    chunks = []
    async for chunk in test_storage_adapter.read_stream(key, chunk_size=500):
        chunks.append(chunk)

    combined = b"".join(chunks)
    assert combined == payload
    assert len(chunks) > 1


def test_controlled_deletion(test_storage_adapter: LocalFilesystemStorageAdapter) -> None:
    """Verify controlled deletion semantics."""
    key = "tmp/cases/CAS-DEL/scratch_to_delete.tmp"
    test_storage_adapter.write(key=key, data=b"Ephemeral")

    assert test_storage_adapter.exists(key) is True
    deleted = test_storage_adapter.delete(key)
    assert deleted is True
    assert test_storage_adapter.exists(key) is False

    # Deleting non-existent returns False without exception
    assert test_storage_adapter.delete(key) is False


def test_path_traversal_prevention(test_storage_adapter: LocalFilesystemStorageAdapter) -> None:
    """Verify path traversal vectors in storage keys are rejected."""
    traversal_keys = [
        "../outside.txt",
        "..\\windows_traversal.txt",
        "originals/../../shadow.txt",
        "/etc/passwd",
        "\\Windows\\System32\\cmd.exe",
    ]
    for bad_key in traversal_keys:
        with pytest.raises(Exception):
            test_storage_adapter.write(bad_key, data=b"Exploit attempt")


def test_staged_storage_transaction_commit(
    test_storage_adapter: LocalFilesystemStorageAdapter,
) -> None:
    """Verify two-phase commit: staged file is moved to permanent key only upon commit."""
    target_key = "originals/cases/CAS-TXN/final_evidence.bin"
    payload = b"Transactional Evidence Data"

    with StagedStorageTransaction(test_storage_adapter) as txn:
        meta = txn.stage_write(target_key, payload)
        assert meta.file_size_bytes == len(payload)
        # Not yet at final target key
        assert test_storage_adapter.exists(target_key) is False
        txn.commit()

    # After commit, file is permanently present
    assert test_storage_adapter.exists(target_key) is True
    assert test_storage_adapter.read(target_key) == payload


def test_staged_storage_transaction_rollback_on_failure(
    test_storage_adapter: LocalFilesystemStorageAdapter,
) -> None:
    """Verify that an aborted transaction purges staged scratch files."""
    target_key = "originals/cases/CAS-FAIL/uncommitted.bin"
    payload = b"Never Persisted"

    try:
        with StagedStorageTransaction(test_storage_adapter) as txn:
            txn.stage_write(target_key, payload)
            # Simulate unexpected database failure before commit
            raise RuntimeError("Database deadlock or constraint violation")
    except RuntimeError:
        pass

    # Target key must not exist
    assert test_storage_adapter.exists(target_key) is False
    # Staging scratch file must have been purged from storage/tmp
    tmp_files = list(test_storage_adapter.manager.tmp_path.iterdir())
    assert all(".txn_stage" not in f.name for f in tmp_files)


def test_cleanup_temporary_files(test_storage_adapter: LocalFilesystemStorageAdapter) -> None:
    """Verify temporary cleanup purges aged files in tmp/."""
    tmp_key = "tmp/abandoned_scratch.tmp"
    test_storage_adapter.write(tmp_key, data=b"Old temp data", allow_overwrite=True)

    # Purge files with 0 second max_age
    purged = cleanup_temporary_files(test_storage_adapter, max_age_seconds=0)
    assert purged >= 1
    assert test_storage_adapter.exists(tmp_key) is False
