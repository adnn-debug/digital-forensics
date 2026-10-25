"""Integration tests for all database repositories."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisStatus, AnalysisType, ArtifactType
from app.db.models.audit import AuditEventType
from app.db.models.case import CaseStatus
from app.db.models.evidence import MediaType, VerificationTrigger
from app.db.models.finding import FindingSeverity, FindingType
from app.db.models.user import UserRole
from app.repositories import (
    AnalysisRepository,
    AuditRepository,
    CaseRepository,
    EvidenceRepository,
    FindingRepository,
    ReportRepository,
    UserRepository,
)
from app.schemas.analysis import (
    AnalysisArtifactCreate,
    ForensicAnalysisCreate,
    ForensicAnalysisUpdate,
)
from app.schemas.audit import AuditEventCreate
from app.schemas.case import CaseCreate, CaseUpdate
from app.schemas.evidence import (
    EvidenceItemCreate,
    HashVerificationCreate,
    MetadataExtractCreate,
)
from app.schemas.finding import FindingCreate, FindingUpdate
from app.schemas.report import ReportCreate
from app.schemas.user import UserCreate


@pytest.mark.asyncio
async def test_user_repository(test_db_session: AsyncSession) -> None:
    """Test user repository creation and lookup by email."""
    repo = UserRepository(test_db_session)

    create_dto = UserCreate(
        email="examiner.john@forensics.agency.gov",
        full_name="John Doe",
        role=UserRole.EXAMINER,
        password="ValidPassword123!",
    )
    user = await repo.create_user(create_dto, hashed_password="argon2_hashed_dummy")
    await test_db_session.commit()

    assert user.id is not None
    assert user.email == "examiner.john@forensics.agency.gov"

    found = await repo.get_by_email("examiner.john@forensics.agency.gov")
    assert found is not None
    assert found.id == user.id

    # Non-existent email lookup
    assert await repo.get_by_email("nonexistent@agency.gov") is None


@pytest.mark.asyncio
async def test_case_repository(test_db_session: AsyncSession) -> None:
    """Test case repository creation, lookup, and status update."""
    user_repo = UserRepository(test_db_session)
    investigator = await user_repo.create_user(
        UserCreate(
            email="lead.sherlock@agency.gov",
            full_name="Sherlock Holmes",
            role=UserRole.ADMIN,
            password="SecurePass999!",
        ),
        hashed_password="hash",
    )
    await test_db_session.flush()

    case_repo = CaseRepository(test_db_session)
    case_dto = CaseCreate(
        case_number="CAS-2026-PERSIST-01",
        title="Operation Bitstream Integrity",
        description="Investigation into modified video surveillance files",
        status=CaseStatus.ACTIVE,
        lead_investigator_id=investigator.id,
    )
    case = await case_repo.create_case(case_dto)
    await test_db_session.commit()

    assert case.id is not None
    assert case.case_number == "CAS-2026-PERSIST-01"

    # Lookup by case number
    loaded = await case_repo.get_by_case_number("CAS-2026-PERSIST-01")
    assert loaded is not None
    assert loaded.id == case.id
    assert loaded.lead_investigator is not None
    assert loaded.lead_investigator.email == "lead.sherlock@agency.gov"

    # Update case status
    updated = await case_repo.update_case(
        case,
        CaseUpdate(status=CaseStatus.ARCHIVED, description="Case concluded and sealed"),
    )
    await test_db_session.commit()
    assert updated.status == CaseStatus.ARCHIVED.value
    assert updated.description == "Case concluded and sealed"

    # List by status
    archived_list = await case_repo.list_by_status(CaseStatus.ARCHIVED)
    assert any(c.id == case.id for c in archived_list)


@pytest.mark.asyncio
async def test_evidence_repository(test_db_session: AsyncSession) -> None:
    """Test evidence repository creation, verification baseline, and metadata extract."""
    case_repo = CaseRepository(test_db_session)
    case = await case_repo.create_case(
        CaseCreate(
            case_number="CAS-2026-EVD-TEST",
            title="Evidence Test Suite",
            status=CaseStatus.ACTIVE,
        )
    )
    await test_db_session.flush()

    evidence_repo = EvidenceRepository(test_db_session)
    sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    evidence_dto = EvidenceItemCreate(
        case_id=case.id,
        evidence_number="EVD-001",
        original_filename="cctv_hallway.mp4",
        stored_filename="vault_cctv_hallway.mp4",
        mime_type="video/mp4",
        media_type=MediaType.VIDEO,
        file_size_bytes=52428800,
        primary_hash_sha256=sha256,
        hash_md5="0123456789abcdef0123456789abcdef",
        hash_sha1="0123456789abcdef0123456789abcdef01234567",
        storage_path="originals/cases/CAS-2026-EVD-TEST/cctv_hallway.mp4",
    )
    item = await evidence_repo.create_evidence(evidence_dto)
    await test_db_session.commit()

    assert item.id is not None
    assert item.primary_hash_sha256 == sha256

    # Lookup by case and evidence number
    fetched = await evidence_repo.get_by_case_and_number(case.id, "EVD-001")
    assert fetched is not None
    assert fetched.id == item.id

    # Lookup by SHA-256
    sha_matches = await evidence_repo.get_by_sha256(sha256)
    assert len(sha_matches) >= 1

    # Add hash verification record
    verify_dto = HashVerificationCreate(
        evidence_id=item.id,
        calculated_sha256=sha256,
        expected_sha256=sha256,
        is_intact=True,
        verification_trigger=VerificationTrigger.PRE_ANALYSIS,
    )
    verification = await evidence_repo.create_hash_verification(verify_dto)
    await test_db_session.commit()
    assert verification.id is not None
    assert verification.is_intact is True

    # Add metadata extract
    meta_dto = MetadataExtractCreate(
        evidence_id=item.id,
        tool_name="FFprobe",
        tool_version="7.0",
        raw_metadata={"streams": [{"codec_name": "h264"}]},
        filtered_forensic_metadata={"codec": "h264", "fps": 30},
    )
    extract = await evidence_repo.create_metadata_extract(meta_dto)
    await test_db_session.commit()
    assert extract.id is not None
    assert extract.tool_name == "FFprobe"


@pytest.mark.asyncio
async def test_analysis_and_finding_repositories(test_db_session: AsyncSession) -> None:
    """Test analysis jobs, derivative artifacts, and forensic findings."""
    case_repo = CaseRepository(test_db_session)
    case = await case_repo.create_case(
        CaseCreate(
            case_number="CAS-2026-ANALYSIS",
            title="Analysis Test Case",
            status=CaseStatus.ACTIVE,
        )
    )
    await test_db_session.flush()

    evidence_repo = EvidenceRepository(test_db_session)
    evidence = await evidence_repo.create_evidence(
        EvidenceItemCreate(
            case_id=case.id,
            evidence_number="EVD-ELA-01",
            original_filename="suspect_badge.jpg",
            stored_filename="vault_suspect_badge.jpg",
            mime_type="image/jpeg",
            media_type=MediaType.IMAGE,
            file_size_bytes=1048576,
            primary_hash_sha256="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            hash_md5="00000000000000000000000000000000",
            hash_sha1="0000000000000000000000000000000000000000",
            storage_path="originals/cases/CAS-2026-ANALYSIS/suspect_badge.jpg",
        )
    )
    await test_db_session.flush()

    analysis_repo = AnalysisRepository(test_db_session)
    analysis_dto = ForensicAnalysisCreate(
        evidence_id=evidence.id,
        analysis_type=AnalysisType.JPEG_ELA,
        parameters={"quality": 90, "multiplier": 15},
        examiner_notes="Searching for badge emblem splicing",
    )
    analysis = await analysis_repo.create_analysis(analysis_dto)
    await test_db_session.commit()

    assert analysis.id is not None
    assert analysis.status == AnalysisStatus.PENDING.value

    # Update analysis to completed
    await analysis_repo.update_analysis(
        analysis,
        ForensicAnalysisUpdate(
            status=AnalysisStatus.COMPLETED,
            summary_results={"max_diff": 45, "mean_diff": 8.2},
        ),
    )
    await test_db_session.commit()
    assert analysis.status == AnalysisStatus.COMPLETED.value

    # Add derivative artifact (ELA Heatmap)
    artifact_dto = AnalysisArtifactCreate(
        analysis_id=analysis.id,
        artifact_type=ArtifactType.ELA_HEATMAP,
        storage_path="artifacts/cases/CAS-2026-ANALYSIS/ela_heatmap.png",
        file_name="ela_heatmap.png",
        mime_type="image/png",
        file_size_bytes=245890,
        hash_sha256="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        artifact_metadata={"scale": "x15"},
    )
    artifact = await analysis_repo.create_artifact(artifact_dto)
    await test_db_session.commit()
    assert artifact.id is not None
    assert artifact.artifact_type == ArtifactType.ELA_HEATMAP.value

    # Add forensic finding
    finding_repo = FindingRepository(test_db_session)
    finding_dto = FindingCreate(
        analysis_id=analysis.id,
        evidence_id=evidence.id,
        finding_type=FindingType.ELA_DISPARITY,
        severity=FindingSeverity.HIGH,
        title="High Error Level Disparity in Central Badge Region",
        description="Pixel compression characteristics in emblem region diverge sharply from surrounding fabric.",
        confidence_score=0.92,
        evidence_offset="x:120,y:250",
        finding_metadata={"anomaly_pixel_count": 4820},
    )
    finding = await finding_repo.create_finding(finding_dto)
    await test_db_session.commit()

    assert finding.id is not None
    assert finding.severity == FindingSeverity.HIGH.value
    assert finding.confidence_score == 0.92

    # Query findings by analysis
    analysis_findings = await finding_repo.list_by_analysis(analysis.id)
    assert len(analysis_findings) == 1
    assert analysis_findings[0].title.startswith("High Error Level")

    # Update finding
    updated_finding = await finding_repo.update_finding(
        finding,
        FindingUpdate(severity=FindingSeverity.CRITICAL, confidence_score=0.98),
    )
    await test_db_session.commit()
    assert updated_finding.severity == FindingSeverity.CRITICAL.value
    assert updated_finding.confidence_score == 0.98


@pytest.mark.asyncio
async def test_report_and_audit_repositories(test_db_session: AsyncSession) -> None:
    """Test report creation and append-only audit event logging."""
    case_repo = CaseRepository(test_db_session)
    case = await case_repo.create_case(
        CaseCreate(
            case_number="CAS-2026-REPORT-01",
            title="Courtroom Presentation Case",
            status=CaseStatus.ACTIVE,
        )
    )
    await test_db_session.flush()

    # Report repository
    report_repo = ReportRepository(test_db_session)
    report_dto = ReportCreate(
        case_id=case.id,
        report_number="REP-2026-COURT-001",
        title="Final Forensic Examination Report",
        storage_path="reports/cases/CAS-2026-REPORT-01/report.pdf",
        file_hash_sha256="dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        file_size_bytes=1048576,
        included_evidence_ids=["evd-1", "evd-2"],
    )
    report = await report_repo.create_report(report_dto)
    await test_db_session.commit()

    assert report.id is not None
    assert report.report_number == "REP-2026-COURT-001"

    found_report = await report_repo.get_by_report_number("REP-2026-COURT-001")
    assert found_report is not None
    assert found_report.id == report.id

    # Audit repository (Append-only)
    audit_repo = AuditRepository(test_db_session)
    event1 = await audit_repo.append_event(
        AuditEventCreate(
            case_id=case.id,
            event_type=AuditEventType.REPORT_GENERATED,
            action_description="Courtroom report REP-2026-COURT-001 compiled and signed",
            event_hash="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        )
    )
    event2 = await audit_repo.append_event(
        AuditEventCreate(
            case_id=case.id,
            event_type=AuditEventType.ARTIFACT_VIEWED,
            action_description="Examiner viewed PDF report seal",
            previous_state_hash=event1.event_hash,
            event_hash="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        )
    )
    await test_db_session.commit()

    assert event1.id is not None
    assert event2.id is not None

    # Chronological list for case
    case_audits = await audit_repo.list_by_case(case.id)
    assert len(case_audits) == 2
    assert case_audits[0].event_type == AuditEventType.REPORT_GENERATED.value
    assert case_audits[1].previous_state_hash == event1.event_hash
