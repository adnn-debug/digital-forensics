"""Safe storage transaction management, temporary file cleanup, and orphan reconciliation.

Two-phase commit pattern
------------------------
1. ``stage_write``  – Writes payload to an isolated tmp staging file and computes
   SHA-256/size metadata.  The permanent vault key is *not* written at this point.
2. ``commit``       – Atomically moves each staging file to its permanent vault key.
3. ``rollback``     – Removes every staging file that has not yet been promoted.
   Called automatically by the context-manager ``__exit__`` when an exception
   escapes the ``with`` block.

Temporary-file cleanup
----------------------
``cleanup_temporary_files`` scans the tmp directory and removes staging files that
are older than ``max_age_seconds`` (default 24 h).  These are abandoned staging
files left behind by crashed processes.

Orphan reconciliation
---------------------
``reconcile_orphaned_files`` cross-references physical files in the permanent
vaults (originals, artifacts, reports) against the three database tables that
record storage keys.  It returns a ``ReconciliationResult`` describing:

  * Disk files with no matching database record (orphans).
  * Database records whose storage key points to a non-existent physical file
    (missing files).

Setting ``auto_clean_orphans=True`` deletes orphaned files during the scan.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import StorageException
from app.db.models.analysis import AnalysisArtifact
from app.db.models.evidence import EvidenceItem
from app.db.models.report import Report
from app.storage.base import StorageFileMetadata
from app.storage.hasher import MultiHasher
from app.storage.local import LocalFilesystemStorageAdapter

logger = logging.getLogger("ps05.storage.transaction")


@dataclass
class StagedItem:
    """Record of a staging file awaiting database-commit confirmation."""

    target_key: str
    staging_path: Path
    metadata: StorageFileMetadata


class StagedStorageTransaction:
    """
    Context manager implementing two-phase commit semantics between storage and database.

    Ensures that if the database commit fails, staged files are removed and
    no unindexed orphan files pollute permanent storage.

    Usage::

        with StagedStorageTransaction(adapter) as txn:
            meta = txn.stage_write(target_key, payload)
            # ... write DB records using meta.hash_sha256 and meta.file_size_bytes ...
            await session.commit()
            txn.commit()          # promote tmp file → vault
        # Exception raised inside the block → txn.__exit__ calls rollback()
    """

    def __init__(self, adapter: LocalFilesystemStorageAdapter) -> None:
        self.adapter = adapter
        self.staged_items: list[StagedItem] = []
        self._committed = False

    def stage_write(
        self,
        key: str,
        data: bytes | BinaryIO,
    ) -> StorageFileMetadata:
        """
        Write payload to an isolated tmp staging file and return metadata.

        The permanent vault key is **not** written at this point.
        Call ``commit()`` after a successful database commit to promote the file.
        """
        target_path = self.adapter._resolve_key_path(key)
        if target_path.exists():
            raise StorageException(
                message=f"Storage key '{key}' already exists. Overwrite forbidden.",
                path=key,
            )

        # Write payload into the tmp staging directory
        staging_filename = f".txn_stage_{uuid4().hex}.tmp"
        staging_path = self.adapter.manager.tmp_path / staging_filename
        staging_path.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        total_bytes = 0

        try:
            with open(staging_path, "wb") as f_out:
                if isinstance(data, bytes):
                    f_out.write(data)
                    hasher.update(data)
                    total_bytes = len(data)
                elif isinstance(data, io.RawIOBase | io.BufferedIOBase):
                    while chunk := data.read(65536):
                        f_out.write(chunk)
                        hasher.update(chunk)
                        total_bytes += len(chunk)
                else:
                    raise StorageException(
                        message=f"Unsupported data type for stage_write: {type(data)}"
                    )
        except Exception as exc:
            if staging_path.exists():
                try:
                    staging_path.unlink()
                except OSError:
                    pass
            if not isinstance(exc, StorageException):
                raise StorageException(
                    message=f"Failed to stage write for key '{key}': {exc}",
                    path=key,
                ) from exc
            raise

        metadata = StorageFileMetadata(
            key=key,
            file_size_bytes=total_bytes,
            hash_sha256=hasher.hexdigest(),
            stored_path_relative=str(target_path.relative_to(self.adapter.manager.base_path)),
        )

        staged = StagedItem(
            target_key=key,
            staging_path=staging_path,
            metadata=metadata,
        )
        self.staged_items.append(staged)
        logger.debug(
            "Staged write for key='%s' at tmp='%s' (%d bytes)",
            key,
            staging_path,
            total_bytes,
        )
        return metadata

    async def stage_stream(
        self,
        key: str,
        stream: Any,
        initial_chunk: bytes = b"",
        max_size_bytes: int | None = None,
        chunk_size: int = 65536,
    ) -> tuple[StorageFileMetadata, str, str]:
        """
        Stream binary payload from an async source directly to a temporary staging file.

        - Bounded memory usage: only chunk_size in memory at any time.
        - Calculates SHA-256, MD5, and SHA-1 in a single streaming pass.
        - Enforces configurable max_size_bytes on the fly; fails fast and cleans up.
        """
        target_path = self.adapter._resolve_key_path(key)
        if target_path.exists():
            raise StorageException(
                message=f"Storage key '{key}' already exists. Overwrite forbidden.",
                path=key,
            )

        staging_filename = f".txn_stage_{uuid4().hex}.tmp"
        staging_path = self.adapter.manager.tmp_path / staging_filename
        staging_path.parent.mkdir(parents=True, exist_ok=True)

        hasher = MultiHasher()
        total_bytes = 0

        try:
            with open(staging_path, "wb") as f_out:
                if initial_chunk:
                    total_bytes += len(initial_chunk)
                    if max_size_bytes is not None and total_bytes > max_size_bytes:
                        raise StorageException(
                            message=f"Uploaded file exceeds maximum limit of {max_size_bytes} bytes.",
                            path=key,
                        )
                    hasher.update(initial_chunk)
                    f_out.write(initial_chunk)

                # Process remainder from async stream
                while True:
                    if hasattr(stream, "read"):
                        # Async file-like object (e.g. Starlette UploadFile)
                        chunk = stream.read(chunk_size)
                        if hasattr(chunk, "__await__"):
                            chunk = await chunk
                    elif hasattr(stream, "__anext__"):
                        try:
                            chunk = await stream.__anext__()
                        except StopAsyncIteration:
                            break
                    else:
                        break

                    if not chunk:
                        break

                    total_bytes += len(chunk)
                    if max_size_bytes is not None and total_bytes > max_size_bytes:
                        raise StorageException(
                            message=f"Uploaded file exceeds maximum limit of {max_size_bytes} bytes.",
                            path=key,
                        )

                    hasher.update(chunk)
                    f_out.write(chunk)

        except Exception as exc:
            if staging_path.exists():
                try:
                    staging_path.unlink()
                except OSError:
                    pass
            if not isinstance(exc, StorageException):
                raise StorageException(
                    message=f"Failed to stream upload for key '{key}': {exc}",
                    path=key,
                ) from exc
            raise

        digests = hasher.finalize()
        metadata = StorageFileMetadata(
            key=key,
            file_size_bytes=total_bytes,
            hash_sha256=digests.sha256,
            stored_path_relative=str(target_path.relative_to(self.adapter.manager.base_path)),
        )

        staged = StagedItem(
            target_key=key,
            staging_path=staging_path,
            metadata=metadata,
        )
        self.staged_items.append(staged)
        logger.debug(
            "Staged streamed write for key='%s' at tmp='%s' (%d bytes, sha256=%s)",
            key,
            staging_path,
            total_bytes,
            metadata.hash_sha256,
        )
        return metadata, digests.md5, digests.sha1

    def commit(self, lock_readonly: bool = True) -> None:
        """Promote all staging files to their permanent vault locations."""
        for item in self.staged_items:
            target_path = self.adapter._resolve_key_path(item.target_key)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if item.staging_path.exists():
                shutil.move(str(item.staging_path), str(target_path))
                if lock_readonly and item.target_key.startswith("originals/"):
                    self.adapter.lock_readonly(item.target_key)
                logger.info(
                    "Committed staged file → key='%s' (%d bytes)",
                    item.target_key,
                    item.metadata.file_size_bytes,
                )
            else:
                logger.warning(
                    "Staged file missing at commit time; skipping: %s",
                    item.staging_path,
                )
        self._committed = True
        self.staged_items.clear()

    def rollback(self) -> None:
        """Purge all uncommitted staging files to prevent storage pollution."""
        for item in self.staged_items:
            if item.staging_path.exists():
                try:
                    item.staging_path.unlink()
                    logger.info("Purged uncommitted staged file: %s", item.staging_path)
                except OSError as exc:
                    logger.warning(
                        "Failed to purge staged file: %s (%s)", item.staging_path, exc
                    )
        self.staged_items.clear()

    def __enter__(self) -> StagedStorageTransaction:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None and not self._committed:
            logger.warning(
                "Storage transaction aborted due to exception: %s. Rolling back staged files...",
                exc_val,
            )
            self.rollback()


# ---------------------------------------------------------------------------
# Temporary-file cleanup
# ---------------------------------------------------------------------------


def cleanup_temporary_files(
    adapter: LocalFilesystemStorageAdapter,
    max_age_seconds: int = 86400,
) -> int:
    """
    Remove abandoned staging files in storage/tmp older than *max_age_seconds*.

    Returns the count of purged files.

    **When to run:** schedule this as a periodic maintenance task (e.g. via the
    Celery beat worker) to reclaim disk space from crashed upload sessions.
    A staging file older than 24 hours almost certainly has no associated
    in-progress transaction.
    """
    tmp_dir = adapter.manager.tmp_path
    if not tmp_dir.exists():
        return 0

    now = time.time()
    purged = 0

    for file_path in tmp_dir.iterdir():
        if file_path.is_file():
            try:
                stat = file_path.stat()
                age = now - stat.st_mtime
                if age > max_age_seconds:
                    file_path.unlink()
                    purged += 1
                    logger.debug(
                        "Purged aged temporary file: %s (age=%.0fs)", file_path, age
                    )
            except OSError as exc:
                logger.warning(
                    "Error inspecting/purging temporary file %s: %s", file_path, exc
                )

    logger.info("Temporary storage cleanup finished. Purged %d stale files.", purged)
    return purged


# ---------------------------------------------------------------------------
# Orphan reconciliation
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationResult:
    """Audit of discrepancy between disk vaults and database records."""

    total_disk_files: int
    total_db_records: int
    orphaned_disk_keys: list[str] = field(default_factory=list)
    missing_file_records: list[str] = field(default_factory=list)


async def reconcile_orphaned_files(
    session: AsyncSession,
    adapter: LocalFilesystemStorageAdapter,
    auto_clean_orphans: bool = False,
) -> ReconciliationResult:
    """
    Cross-reference permanent vault directories against database storage keys.

    Detects:

    1. **Orphaned files** – physical files on disk not referenced by any DB row.
    2. **Missing files** – DB rows whose ``storage_path`` points to a key that
       does not exist on disk.

    Parameters
    ----------
    session:
        Active async database session (read-only queries).
    adapter:
        Local filesystem storage adapter (provides vault paths).
    auto_clean_orphans:
        When *True*, orphaned files are deleted from disk during the scan.
        Use with caution; only enable during scheduled maintenance windows.

    Returns
    -------
    ReconciliationResult
        Populated with counts and key lists for further action.
    """
    # 1. Collect all known storage keys from the database
    db_paths: set[str] = set()

    ev_res = await session.execute(select(EvidenceItem.storage_path))
    db_paths.update(p for p in ev_res.scalars().all() if p is not None)

    art_res = await session.execute(select(AnalysisArtifact.storage_path))
    db_paths.update(p for p in art_res.scalars().all() if p is not None)

    rep_res = await session.execute(select(Report.storage_path))
    db_paths.update(p for p in rep_res.scalars().all() if p is not None)

    # 2. Collect all physical files in permanent vaults (exclude tmp)
    disk_keys: set[str] = set()
    vault_dirs = [
        adapter.manager.originals_path,
        adapter.manager.artifacts_path,
        adapter.manager.reports_path,
    ]

    for vault_dir in vault_dirs:
        if vault_dir.exists():
            for root, _, files in os.walk(vault_dir):
                for f in files:
                    if not f.startswith("."):
                        full_p = Path(root) / f
                        rel_p = full_p.relative_to(adapter.manager.base_path)
                        key_str = str(rel_p).replace("\\", "/")
                        disk_keys.add(key_str)

    # 3. Normalize and compare
    normalized_db_keys = {p.replace("\\", "/") for p in db_paths}

    orphaned = [k for k in disk_keys if k not in normalized_db_keys]
    missing = [k for k in normalized_db_keys if k not in disk_keys]

    if auto_clean_orphans and orphaned:
        for orphan_key in orphaned:
            try:
                adapter.delete(orphan_key)
                logger.warning("Auto-cleaned orphaned storage file: %s", orphan_key)
            except StorageException as exc:
                logger.error("Failed to auto-clean orphan '%s': %s", orphan_key, exc)

    result = ReconciliationResult(
        total_disk_files=len(disk_keys),
        total_db_records=len(normalized_db_keys),
        orphaned_disk_keys=orphaned,
        missing_file_records=missing,
    )

    logger.info(
        "Storage reconciliation complete. Disk=%d DB=%d Orphans=%d Missing=%d",
        len(disk_keys),
        len(normalized_db_keys),
        len(orphaned),
        len(missing),
    )
    return result
