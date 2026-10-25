"""Integration tests verifying ORM models, relationships, and constraints."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AnalysisArtifact,
    AnalysisStatus,
    AnalysisType,
    ArtifactType,
    AuditEvent,
    AuditEventType,
    Case,
    CaseStatus,
    EvidenceItem,
    ForensicAnalysis,
    HashVerification,
    MediaType,
    MetadataExtract,
    Report,
    User,
    UserRole,
    VerificationTrigger,
)


@pytest.mark.asyncio
async def test_full_domain_lifecycle_and_relationships(test_db_session: AsyncSession) -> None:
    """Verify entity creation and relational integrity across the domain graph."""
    # 1. Create Examiner User
    examiner = User(
        id=uuid4(),
        email="examiner@forensics.agency.gov",
        hashed_password="argon2id_mock_hash",
        full_name="Agent Dana Scully",
        role=UserRole.EXAMINER.value,
        is_active=True,
    )
    test_db_session.add(examiner)
    await test_db_session.flush()

    # 2. Create Case assigned to Examiner
    case = Case(
        id=uuid4(),
        case_number="CAS-2026-X01",
        title="Operation Cyber Safeguard",
        description="Forensic investigation into altered surveillance bitstreams",
        status=CaseStatus.ACTIVE.value,
        lead_investigator_id=examiner.id,
    )
    test_db_session.add(case)
    await test_db_session.flush()

    # 3. Create Evidence Item under Case
    evidence = EvidenceItem(
        id=uuid4(),
        case_id=case.id,
        evidence_number="EVD-001",
        original_filename="tampered_cctv.mp4",
        stored_filename="vault_tampered_cctv.mp4",
        mime_type="video/mp4",
        media_type=MediaType.VIDEO.value,
        file_size_bytes=104857600,
        primary_hash_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        hash_md5="098f6bcd4621d373cade4e832627b4f6",
        hash_sha1="a9993e364706816aba3e25717850c26c9cd0d89d",
        storage_path="cases/CAS-2026-X01/evidence/EVD-001/vault_tampered_cctv.mp4",
        is_quarantined=False,
        uploaded_by_id=examiner.id,
    )
    test_db_session.add(evidence)
    await test_db_session.flush()

    # 4. Create Initial Hash Baseline Verification
    verification = HashVerification(
        id=uuid4(),
        evidence_id=evidence.id,
        calculated_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        expected_sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        is_intact=True,
        verification_trigger=VerificationTrigger.PRE_ANALYSIS.value,
        verified_by_id=examiner.id,
    )
    test_db_session.add(verification)

    # 5. Create Metadata Extract
    metadata_extract = MetadataExtract(
        id=uuid4(),
        evidence_id=evidence.id,
        tool_name="FFprobe",
        tool_version="7.0",
        raw_metadata={"streams": [{"codec_name": "h264", "duration": "120.5"}]},
        filtered_forensic_metadata={"codec": "h264", "duration_sec": 120.5, "fps": 30},
    )
    test_db_session.add(metadata_extract)

    # 6. Create Forensic Analysis and Artifact
    analysis = ForensicAnalysis(
        id=uuid4(),
        evidence_id=evidence.id,
        analysis_type=AnalysisType.VIDEO_FRAMES.value,
        status=AnalysisStatus.COMPLETED.value,
        parameters={"interval_seconds": 5},
        summary_results={"total_keyframes": 24, "scene_changes": 3},
        initiated_by_id=examiner.id,
    )
    test_db_session.add(analysis)
    await test_db_session.flush()

    artifact = AnalysisArtifact(
        id=uuid4(),
        analysis_id=analysis.id,
        artifact_type=ArtifactType.KEYFRAME_IMAGE.value,
        storage_path="artifacts/keyframe_001.png",
        file_name="keyframe_001.png",
        mime_type="image/png",
        file_size_bytes=245890,
        hash_sha256="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        artifact_metadata={"frame_timestamp_sec": 5.0},
    )
    test_db_session.add(artifact)

    # 7. Create Courtroom Report
    report = Report(
        id=uuid4(),
        case_id=case.id,
        report_number="REP-2026-X01-001",
        title="Comprehensive Examination Report: CCTV Analysis",
        generated_by_id=examiner.id,
        storage_path="reports/REP-2026-X01-001.pdf",
        file_hash_sha256="fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321",
        file_size_bytes=1048576,
        included_evidence_ids=[str(evidence.id)],
    )
    test_db_session.add(report)

    # 8. Create Audit Event
    audit = AuditEvent(
        id=uuid4(),
        case_id=case.id,
        evidence_id=evidence.id,
        user_id=examiner.id,
        event_type=AuditEventType.REPORT_GENERATED.value,
        action_description="Courtroom PDF report compiled and sealed with SHA-256",
        event_hash="33334444555566667777888899990000aaaabbbbccccddddeeeeffff00001111",
        payload_delta={"report_number": "REP-2026-X01-001"},
    )
    test_db_session.add(audit)
    await test_db_session.commit()

    from sqlalchemy.orm import selectinload

    # Query and assert relationships using async selectinload
    stmt = (
        select(Case)
        .where(Case.id == case.id)
        .options(
            selectinload(Case.lead_investigator),
            selectinload(Case.reports),
            selectinload(Case.evidence_items).selectinload(EvidenceItem.hash_verifications),
            selectinload(Case.evidence_items).selectinload(EvidenceItem.metadata_extracts),
            selectinload(Case.evidence_items)
            .selectinload(EvidenceItem.forensic_analyses)
            .selectinload(ForensicAnalysis.artifacts),
        )
    )
    res = await test_db_session.execute(stmt)
    loaded_case = res.scalar_one()

    assert loaded_case.case_number == "CAS-2026-X01"
    assert len(loaded_case.evidence_items) == 1
    assert loaded_case.evidence_items[0].original_filename == "tampered_cctv.mp4"
    assert len(loaded_case.evidence_items[0].hash_verifications) == 1
    assert len(loaded_case.evidence_items[0].metadata_extracts) == 1
    assert len(loaded_case.evidence_items[0].forensic_analyses) == 1
    assert len(loaded_case.evidence_items[0].forensic_analyses[0].artifacts) == 1
    assert len(loaded_case.reports) == 1
    assert loaded_case.lead_investigator is not None
    assert loaded_case.lead_investigator.email == "examiner@forensics.agency.gov"
