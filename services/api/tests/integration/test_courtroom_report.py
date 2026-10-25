"""Integration tests for Courtroom Forensic Examination Reports."""

import io
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import UploadFile
import httpx
import pypdf
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token
from app.db.models.case import Case
from app.db.models.user import User, UserRole
from app.services.evidence_service import EvidenceService
from app.storage.local import LocalFilesystemStorageAdapter


@pytest.fixture
async def report_test_context(
    test_db_session: AsyncSession,
    test_storage_adapter: LocalFilesystemStorageAdapter,
    test_settings: Settings,
) -> dict[str, Any]:
    """Seed an examiner user, a case, and ingested evidence for reporting tests."""
    examiner = User(
        id=uuid4(),
        email="lead.examiner@forensics.test",
        hashed_password="hashedpassword123",
        full_name="Special Agent Marcus Vance",
        role=UserRole.EXAMINER.value,
        is_active=True,
    )
    test_db_session.add(examiner)
    await test_db_session.commit()

    case = Case(
        id=uuid4(),
        case_number="CASE-2026-REPORT-01",
        title="Operation Silent Byte",
        description="Forensic investigation into intercepted media storage.",
        lead_investigator_id=examiner.id,
    )
    test_db_session.add(case)
    await test_db_session.commit()

    class MockUploadFile:
        def __init__(self, filename: str, content: bytes, content_type: str = "image/gif") -> None:
            self.filename = filename
            self.content_type = content_type
            self._stream = io.BytesIO(content)

        async def read(self, size: int = -1) -> bytes:
            return self._stream.read(size)

        async def seek(self, offset: int) -> None:
            self._stream.seek(offset)

    gif_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    mock_file = MockUploadFile("intercepted_visual.gif", gif_bytes, "image/gif")

    evidence_service = EvidenceService(test_db_session, test_storage_adapter)
    evidence = await evidence_service.ingest_evidence(
        case_id=case.id,
        file=cast(UploadFile, mock_file),
        current_user=examiner,
        evidence_number="EVID-RPT-001",
        settings=test_settings,
    )

    token = create_access_token(subject=examiner.id, role=examiner.role)
    headers = {"Authorization": f"Bearer {token}"}

    return {
        "examiner": examiner,
        "case": case,
        "evidence": evidence,
        "headers": headers,
    }


@pytest.mark.asyncio
async def test_generate_and_download_courtroom_report(
    async_client: httpx.AsyncClient,
    report_test_context: dict[str, Any],
) -> None:
    """Verify courtroom report generation, hash sealing, listing, and PDF download."""
    case_id = report_test_context["case"].id
    headers = report_test_context["headers"]

    # 1. Generate Report
    payload = {
        "title": "Comprehensive Certified Forensics Report",
    }
    resp = await async_client.post(
        f"/api/v1/cases/{case_id}/reports/generate",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 201
    report_data = resp.json()

    assert "id" in report_data
    assert report_data["case_id"] == str(case_id)
    assert report_data["report_number"].startswith("REP-CASE-2026-REPORT-01-")
    assert len(report_data["file_hash_sha256"]) == 64
    assert report_data["file_size_bytes"] > 1000

    report_id = report_data["id"]

    # 2. List Reports for Case
    list_resp = await async_client.get(
        f"/api/v1/cases/{case_id}/reports",
        headers=headers,
    )
    assert list_resp.status_code == 200
    reports_list = list_resp.json()
    assert len(reports_list) >= 1
    assert any(r["id"] == report_id for r in reports_list)

    # 3. Get Specific Report Metadata
    meta_resp = await async_client.get(
        f"/api/v1/cases/{case_id}/reports/{report_id}",
        headers=headers,
    )
    assert meta_resp.status_code == 200
    assert meta_resp.json()["report_number"] == report_data["report_number"]

    # 4. Download Sealed PDF Bytes
    dl_resp = await async_client.get(
        f"/api/v1/cases/{case_id}/reports/{report_id}/download",
        headers=headers,
    )
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in dl_resp.headers["content-disposition"]
    pdf_bytes = dl_resp.content

    assert pdf_bytes.startswith(b"%PDF-")
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1

    extracted_text = " ".join("".join(p.extract_text() for p in reader.pages).split())
    assert "Operation Silent Byte" in extracted_text
    assert "Special Agent Marcus Vance" in extracted_text
    assert "EVID-RPT-001" in extracted_text
    assert "intercepted_visual.gif" in extracted_text
    assert "CHAIN OF CUSTODY" in extracted_text
