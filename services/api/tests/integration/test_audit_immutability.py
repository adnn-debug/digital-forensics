"""Integration tests verifying database-level immutability and anti-tamper triggers."""

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent, AuditEventType
from app.db.models.case import Case, CaseStatus
from app.db.models.evidence import EvidenceItem, MediaType


@pytest.mark.asyncio
async def test_audit_log_cannot_be_updated(test_db_session: AsyncSession) -> None:
    """Verify database trigger rejects any UPDATE on audit_events."""
    event_id = uuid4()
    audit_event = AuditEvent(
        id=event_id,
        event_type=AuditEventType.EVIDENCE_INGESTED.value,
        action_description="Initial evidence ingestion",
        event_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    test_db_session.add(audit_event)
    await test_db_session.commit()

    # Attempt to tamper with the audit record description (Must raise Database Exception)
    with pytest.raises(Exception) as exc_info:
        await test_db_session.execute(
            text("UPDATE audit_events SET action_description = 'TAMPERED'")
        )
        await test_db_session.commit()

    await test_db_session.rollback()
    assert "CRITICAL SECURITY VIOLATION" in str(exc_info.value)

    # Verify original content remains intact
    stmt = select(AuditEvent).where(AuditEvent.id == event_id)
    result = await test_db_session.execute(stmt)
    saved = result.scalar_one()
    assert saved.action_description == "Initial evidence ingestion"


@pytest.mark.asyncio
async def test_audit_log_cannot_be_deleted(test_db_session: AsyncSession) -> None:
    """Verify database trigger rejects any DELETE on audit_events."""
    event_id = uuid4()
    audit_event = AuditEvent(
        id=event_id,
        event_type=AuditEventType.HASH_VERIFIED.value,
        action_description="Baseline hash verified intact",
        event_hash="ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
    )
    test_db_session.add(audit_event)
    await test_db_session.commit()

    # Attempt to delete the audit record (Must raise Database Exception)
    with pytest.raises(Exception) as exc_info:
        await test_db_session.execute(text("DELETE FROM audit_events"))
        await test_db_session.commit()

    await test_db_session.rollback()
    assert "CRITICAL SECURITY VIOLATION" in str(exc_info.value)

    # Verify record still exists
    stmt = select(AuditEvent).where(AuditEvent.id == event_id)
    result = await test_db_session.execute(stmt)
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_evidence_primary_hash_cannot_be_modified(test_db_session: AsyncSession) -> None:
    """Verify database trigger rejects altering primary_hash_sha256 on evidence_items."""
    case_id = uuid4()
    case = Case(
        id=case_id,
        case_number="CAS-2026-TEST-01",
        title="Tamper Test Case",
        status=CaseStatus.ACTIVE.value,
    )
    test_db_session.add(case)

    evidence_id = uuid4()
    evidence = EvidenceItem(
        id=evidence_id,
        case_id=case_id,
        evidence_number="EVD-001",
        original_filename="cctv_frame.jpg",
        stored_filename="stored_cctv_frame.jpg",
        mime_type="image/jpeg",
        media_type=MediaType.IMAGE.value,
        file_size_bytes=10240,
        primary_hash_sha256="1111111111111111111111111111111111111111111111111111111111111111",
        hash_md5="d41d8cd98f00b204e9800998ecf8427e",
        hash_sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        storage_path="cases/CAS-2026-TEST-01/evidence/EVD-001/cctv_frame.jpg",
    )
    test_db_session.add(evidence)
    await test_db_session.commit()

    # Attempt to modify primary_hash_sha256
    new_hash = "9" * 64
    with pytest.raises(Exception) as exc_info:
        await test_db_session.execute(
            text(f"UPDATE evidence_items SET primary_hash_sha256 = '{new_hash}'")
        )
        await test_db_session.commit()

    await test_db_session.rollback()
    assert "CRITICAL SECURITY VIOLATION" in str(exc_info.value)
