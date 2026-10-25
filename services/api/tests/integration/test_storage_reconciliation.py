"""Integration tests for storage reconciliation and failure recovery."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.case import Case, CaseStatus
from app.db.models.evidence import EvidenceItem, MediaType
from app.storage.local import LocalFilesystemStorageAdapter
from app.storage.transaction import (
    StagedStorageTransaction,
    reconcile_orphaned_files,
)


@pytest.mark.asyncio
async def test_reconciliation_detects_orphaned_and_missing_files(
    test_db_session: AsyncSession,
    test_storage_adapter: LocalFilesystemStorageAdapter,
) -> None:
    """Verify that reconcile_orphaned_files correctly flags discrepancies between disk and DB."""
    # 1. Create a synchronized record (exists on disk and in DB)
    synced_key = "originals/cases/CAS-SYNC/synced_file.jpg"
    synced_meta = test_storage_adapter.write(synced_key, b"Synchronized Evidence")

    case_id = uuid4()
    case = Case(
        id=case_id,
        case_number="CAS-SYNC-01",
        title="Sync Case",
        status=CaseStatus.ACTIVE.value,
    )
    test_db_session.add(case)

    evidence_synced = EvidenceItem(
        id=uuid4(),
        case_id=case_id,
        evidence_number="EVD-SYNC-01",
        original_filename="synced_file.jpg",
        stored_filename="synced_file.jpg",
        mime_type="image/jpeg",
        media_type=MediaType.IMAGE.value,
        file_size_bytes=synced_meta.file_size_bytes,
        primary_hash_sha256=synced_meta.hash_sha256,
        hash_md5="0" * 32,
        hash_sha1="0" * 40,
        storage_path=synced_key,
    )
    test_db_session.add(evidence_synced)

    # 2. Create a missing file in DB (DB record exists, but physical file deleted/missing)
    missing_key = "originals/cases/CAS-SYNC/missing_on_disk.bin"
    evidence_missing = EvidenceItem(
        id=uuid4(),
        case_id=case_id,
        evidence_number="EVD-MISS-01",
        original_filename="missing_on_disk.bin",
        stored_filename="missing_on_disk.bin",
        mime_type="application/octet-stream",
        media_type=MediaType.IMAGE.value,
        file_size_bytes=100,
        primary_hash_sha256="1" * 64,
        hash_md5="1" * 32,
        hash_sha1="1" * 40,
        storage_path=missing_key,
    )
    test_db_session.add(evidence_missing)
    await test_db_session.commit()

    # 3. Create an unindexed orphan file on disk (physical file exists, no DB record)
    orphan_key = "originals/cases/CAS-SYNC/orphan_rogue_file.raw"
    test_storage_adapter.write(orphan_key, b"Rogue Bitstream")

    # Run reconciliation
    audit_report = await reconcile_orphaned_files(
        session=test_db_session,
        adapter=test_storage_adapter,
        auto_clean_orphans=False,
    )

    assert orphan_key in audit_report.orphaned_disk_keys
    assert missing_key in audit_report.missing_file_records
    assert synced_key not in audit_report.orphaned_disk_keys
    assert synced_key not in audit_report.missing_file_records

    # 4. Now run reconciliation with auto_clean_orphans=True
    clean_report = await reconcile_orphaned_files(
        session=test_db_session,
        adapter=test_storage_adapter,
        auto_clean_orphans=True,
    )
    # The orphan must have been deleted from disk
    assert test_storage_adapter.exists(orphan_key) is False


@pytest.mark.asyncio
async def test_atomic_storage_db_transaction_failure_handling(
    test_db_session: AsyncSession,
    test_storage_adapter: LocalFilesystemStorageAdapter,
) -> None:
    """Verify failure rollback ensures no orphan files remain when DB transaction fails."""
    target_key = "originals/cases/CAS-ROLLBACK/evidence_attempt.mp4"
    payload = b"Large 4K Surveillance Video Stream"

    try:
        with StagedStorageTransaction(test_storage_adapter) as txn:
            meta = txn.stage_write(target_key, payload)

            # Intentionally induce a database error (foreign key violation)
            invalid_evidence = EvidenceItem(
                id=uuid4(),
                case_id=uuid4(),  # Does not exist in cases table
                evidence_number="EVD-FAIL-01",
                original_filename="evidence_attempt.mp4",
                stored_filename="evidence_attempt.mp4",
                mime_type="video/mp4",
                media_type=MediaType.VIDEO.value,
                file_size_bytes=meta.file_size_bytes,
                primary_hash_sha256=meta.hash_sha256,
                hash_md5="2" * 32,
                hash_sha1="2" * 40,
                storage_path=target_key,
            )
            test_db_session.add(invalid_evidence)
            # This commit will fail due to foreign key or trigger
            await test_db_session.commit()
            txn.commit()
    except Exception:
        await test_db_session.rollback()

    # Verify target file was never created in permanent storage
    assert test_storage_adapter.exists(target_key) is False

    # Verify reconciliation finds zero orphaned files
    audit = await reconcile_orphaned_files(
        session=test_db_session,
        adapter=test_storage_adapter,
    )
    assert target_key not in audit.orphaned_disk_keys
