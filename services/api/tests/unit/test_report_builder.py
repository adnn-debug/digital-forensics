"""Unit tests for CourtroomReportBuilder and NumberedCanvas."""

import io
from pathlib import Path

import pypdf
import pytest

from app.reports.builder import (
    CourtroomReportBuilder,
    CourtroomReportData,
    ReportAnalysisData,
    ReportArtifactData,
    ReportAuditEventData,
    ReportEvidenceItemData,
    ReportFindingData,
)


@pytest.fixture
def sample_report_data() -> CourtroomReportData:
    """Generate structured courtroom report input data."""
    evidence = [
        ReportEvidenceItemData(
            evidence_number="EVID-2026-001",
            original_filename="crime_scene_photo.jpg",
            media_type="IMAGE",
            file_size_bytes=204800,
            primary_hash_sha256="a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0",
            hash_md5="0123456789abcdef0123456789abcdef",
            hash_sha1="0123456789abcdef0123456789abcdef01234567",
            ingested_at="2026-10-25T10:00:00Z",
            is_intact=True,
        )
    ]

    audit = [
        ReportAuditEventData(
            timestamp="2026-10-25T10:00:00Z",
            user_name="Detective John Miller",
            event_type="EVIDENCE_INGESTED",
            action_description="Initial cryptographic intake and 0400 vault lock.",
            event_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        ReportAuditEventData(
            timestamp="2026-10-25T10:05:00Z",
            user_name="SYSTEM_AUDITOR",
            event_type="HASH_VERIFIED",
            action_description="Cryptographic re-verification intact.",
            event_hash="ca978112ca1bbdcafac231b39a23dc4da78608144160984cca25094f5ec6dddd",
        ),
    ]

    analyses = [
        ReportAnalysisData(
            analysis_type="JPEG_ELA",
            status="COMPLETED",
            completed_at="2026-10-25T10:10:00Z",
            summary_results={"mean_error": 12.4, "scale": 15.0},
            findings=[
                ReportFindingData(
                    finding_type="ELA_DISPARITY",
                    severity="LOW",
                    title="Compression Boundary Evaluated",
                    description="No anomalous high-disparity regions detected across grid blocks.",
                    confidence_score=0.92,
                )
            ],
            artifacts=[],
        )
    ]

    return CourtroomReportData(
        case_number="CASE-2026-7890",
        case_title="State v. Suspect - Electronic Forensics",
        case_description="Digital evidence verification for physical drive recovery.",
        opened_at="2026-10-20T08:00:00Z",
        examiner_name="Special Agent Sarah Connor",
        examiner_role="Senior Forensic Analyst",
        examiner_email="sconnor@forensics.gov",
        report_number="REP-2026-00042",
        report_title="Courtroom Evidentiary Examination and Chain of Custody Report",
        generated_at="2026-10-25T12:00:00Z",
        evidence_items=evidence,
        audit_events=audit,
        analyses=analyses,
        verification_url="https://verify.forensics.state.gov",
    )


def test_courtroom_report_builder_pdf_generation(sample_report_data: CourtroomReportData) -> None:
    """Verify that CourtroomReportBuilder produces valid, parsable courtroom PDF."""
    builder = CourtroomReportBuilder()
    pdf_bytes = builder.build_pdf(sample_report_data)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")

    # Parse with pypdf to verify validity and extract text
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    extracted_text = "".join(page.extract_text() for page in reader.pages)

    # Normalize whitespace for multi-line wrapped text
    clean_text = " ".join(extracted_text.split())

    # Assert presence of critical legal metadata
    assert "DIGITAL EVIDENCE EXAMINATION REPORT" in clean_text
    assert sample_report_data.case_number in clean_text
    assert sample_report_data.report_number in clean_text
    assert sample_report_data.examiner_name in clean_text
    assert "CHAIN OF CUSTODY" in clean_text
    assert "EVID-2026-00" in clean_text
    assert "crime_scene_photo.jpg" in clean_text
    assert "CERTIFICATION OF AUTHENTICITY" in clean_text
