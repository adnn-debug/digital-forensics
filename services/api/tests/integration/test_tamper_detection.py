"""Integration tests for VerificationService, tamper detection, and bit-flip alerting."""

from __future__ import annotations

import io
import stat
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.db.models.audit import AuditEvent, AuditEventType
from app.db.models.case import Case, CaseStatus
from app.db.models.evidence import VerificationTrigger
from app.db.models.user import User, UserRole
from app.services.evidence_service import EvidenceService
from app.services.verification_service import VerificationService
from app.storage.local import LocalFilesystemStorageAdapter

VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xef\x8c\x8e\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MockUploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str = "image/png") -> None:
        self.filename = filename
        self.content_type = content_type
        self._stream = io.BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    async def seek(self, offset: int) -> None:
        self._stream.seek(offset)


@pytest.mark.asyncio
async def test_tamper_detection_and_bit_flip_alerting(
    test_db_session: AsyncSession,
    test_storage_adapter: LocalFilesystemStorageAdapter,
    test_settings: Settings,
) -> None:
    """Verify that a single bit-flip on disk is immediately flagged as TAMPER_DETECTED."""
    user = User(
        id=uuid4(),
        email=f"tamper_{uuid4().hex[:6]}@agency.gov",
        hashed_password=hash_password("SafeSecretPass123!"),
        full_name="Forensic Auditor",
        role=UserRole.EXAMINER.value,
        is_active=True,
    )
    test_db_session.add(user)

    case = Case(
        id=uuid4(),
        case_number=f"CAS-TAMPER-{uuid4().hex[:6].upper()}",
        title="Tamper Detection Case",
        lead_investigator_id=user.id,
        status=CaseStatus.ACTIVE.value,
    )
    test_db_session.add(case)
    await test_db_session.commit()

    # 1. Ingest evidence
    upload = MockUploadFile(filename="original_image.png", content=VALID_PNG_BYTES)
    evidence_service = EvidenceService(test_db_session, test_storage_adapter)
    item = await evidence_service.ingest_evidence(
        case_id=case.id,
        file=upload,  # type: ignore[arg-type]
        evidence_number="EVD-TAMPER-001",
        current_user=user,
        settings=test_settings,
    )

    verif_service = VerificationService(test_db_session, test_storage_adapter)

    # 2. Baseline re-verification when file is intact
    res_intact = await verif_service.verify_evidence_integrity(
        case_id=case.id,
        evidence_id=item.id,
        trigger=VerificationTrigger.MANUAL,
        current_user=user,
    )
    assert res_intact.is_intact is True
    assert res_intact.calculated_sha256 == item.primary_hash_sha256

    # 3. Simulate hostile bit-flip tampering on disk
    file_path = test_storage_adapter.get_local_path_readonly(item.storage_path)
    # Temporarily allow writing to simulate attacker
    file_path.chmod(stat.S_IWRITE | stat.S_IWUSR)
    corrupted_bytes = bytearray(VALID_PNG_BYTES)
    corrupted_bytes[-1] ^= 0x01  # Flip a single bit
    file_path.write_bytes(bytes(corrupted_bytes))
    # Re-lock permissions
    file_path.chmod(stat.S_IRUSR | stat.S_IREAD)

    # 4. Re-verify integrity — must detect tamper
    res_tampered = await verif_service.verify_evidence_integrity(
        case_id=case.id,
        evidence_id=item.id,
        trigger=VerificationTrigger.SCHEDULED_ROUTINE,
        current_user=user,
    )
    assert res_tampered.is_intact is False
    assert res_tampered.calculated_sha256 != res_tampered.expected_sha256

    # 5. Verify immutable TAMPER_DETECTED audit event is logged
    tamper_audit_stmt = select(AuditEvent).where(
        AuditEvent.evidence_id == item.id,
        AuditEvent.event_type == AuditEventType.TAMPER_DETECTED.value,
    )
    audit_res = await test_db_session.execute(tamper_audit_stmt)
    tamper_event = audit_res.scalar_one_or_none()
    assert tamper_event is not None
    assert "CRITICAL: Cryptographic hash mismatch" in tamper_event.action_description
    assert tamper_event.payload_delta is not None
    assert tamper_event.payload_delta["is_intact"] is False
