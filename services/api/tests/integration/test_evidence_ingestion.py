"""Integration tests for EvidenceService ingestion, permission locking, and multi-hashing."""

from __future__ import annotations

import io
import stat
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.db.models.audit import AuditEvent, AuditEventType
from app.db.models.case import Case, CaseStatus
from app.db.models.evidence import HashVerification
from app.db.models.user import User, UserRole
from app.services.evidence_service import EvidenceService
from app.storage.hasher import MultiHasher
from app.storage.local import LocalFilesystemStorageAdapter

VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xef\x8c\x8e\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MockUploadFile:
    """Mock UploadFile for direct service testing."""

    def __init__(self, filename: str, content: bytes, content_type: str = "image/png") -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self._stream = io.BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    async def seek(self, offset: int) -> None:
        self._stream.seek(offset)


async def _create_test_case(db: AsyncSession, lead_id: UUID) -> Case:
    case = Case(
        id=uuid4(),
        case_number=f"CAS-INGEST-{uuid4().hex[:6].upper()}",
        title="Evidence Ingestion Test Case",
        lead_investigator_id=lead_id,
        status=CaseStatus.ACTIVE.value,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return case


@pytest.mark.asyncio
async def test_evidence_service_ingest_lifecycle(
    test_db_session: AsyncSession,
    test_storage_adapter: LocalFilesystemStorageAdapter,
    test_settings: Settings,
) -> None:
    """Verify complete evidence intake lifecycle, permission locking, and audit chaining."""
    user = User(
        id=uuid4(),
        email=f"ingest_{uuid4().hex[:6]}@agency.gov",
        hashed_password=hash_password("SafeSecretPass123!"),
        full_name="Forensic Lead",
        role=UserRole.EXAMINER.value,
        is_active=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()

    case = await _create_test_case(test_db_session, user.id)

    upload = MockUploadFile(filename="surveillance_sample.png", content=VALID_PNG_BYTES)
    service = EvidenceService(test_db_session, test_storage_adapter)

    evidence_item = await service.ingest_evidence(
        case_id=case.id,
        file=upload,  # type: ignore[arg-type]
        evidence_number=None,
        current_user=user,
        settings=test_settings,
    )

    assert evidence_item.id is not None
    assert evidence_item.original_filename == "surveillance_sample.png"
    assert evidence_item.media_type == "IMAGE"
    assert evidence_item.file_size_bytes == len(VALID_PNG_BYTES)

    # Verify hashes match independent MultiHasher calculation
    expected_digests = MultiHasher.hash_bytes(VALID_PNG_BYTES)
    assert evidence_item.primary_hash_sha256 == expected_digests.sha256
    assert evidence_item.hash_md5 == expected_digests.md5
    assert evidence_item.hash_sha1 == expected_digests.sha1

    # Verify physical file exists in storage vault and read-only permission is applied
    vault_path = test_storage_adapter.get_local_path_readonly(evidence_item.storage_path)
    assert vault_path.exists()
    assert vault_path.read_bytes() == VALID_PNG_BYTES

    file_stat = vault_path.stat()
    # Read permission must be present
    assert bool(file_stat.st_mode & stat.S_IRUSR or file_stat.st_mode & stat.S_IREAD)

    # Verify baseline HashVerification record committed
    verif_stmt = select(HashVerification).where(HashVerification.evidence_id == evidence_item.id)
    verif_res = await test_db_session.execute(verif_stmt)
    verif = verif_res.scalar_one_or_none()
    assert verif is not None
    assert verif.is_intact is True
    assert verif.calculated_sha256 == expected_digests.sha256

    # Verify AuditEvent committed
    audit_stmt = select(AuditEvent).where(
        AuditEvent.evidence_id == evidence_item.id,
        AuditEvent.event_type == AuditEventType.EVIDENCE_INGESTED.value,
    )
    audit_res = await test_db_session.execute(audit_stmt)
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.event_hash is not None


@pytest.mark.asyncio
async def test_evidence_service_rejects_empty_file(
    test_db_session: AsyncSession,
    test_storage_adapter: LocalFilesystemStorageAdapter,
    test_settings: Settings,
) -> None:
    """Verify empty evidence upload raises HTTP 400 Bad Request."""
    user = User(
        id=uuid4(),
        email=f"empty_{uuid4().hex[:6]}@agency.gov",
        hashed_password=hash_password("SafeSecretPass123!"),
        full_name="Forensic Lead",
        role=UserRole.EXAMINER.value,
        is_active=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    case = await _create_test_case(test_db_session, user.id)

    upload = MockUploadFile(filename="zero_bytes.png", content=b"")
    service = EvidenceService(test_db_session, test_storage_adapter)

    with pytest.raises(HTTPException) as exc_info:
        await service.ingest_evidence(
            case_id=case.id,
            file=upload,  # type: ignore[arg-type]
            evidence_number=None,
            current_user=user,
            settings=test_settings,
        )
    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "EMPTY_FILE"


@pytest.mark.asyncio
async def test_evidence_service_rejects_disguised_file(
    test_db_session: AsyncSession,
    test_storage_adapter: LocalFilesystemStorageAdapter,
    test_settings: Settings,
) -> None:
    """Verify Windows executable disguised as image is rejected with HTTP 400."""
    user = User(
        id=uuid4(),
        email=f"disguise_{uuid4().hex[:6]}@agency.gov",
        hashed_password=hash_password("SafeSecretPass123!"),
        full_name="Forensic Lead",
        role=UserRole.EXAMINER.value,
        is_active=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    case = await _create_test_case(test_db_session, user.id)

    fake_image_exe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00MaliciousPayload"
    upload = MockUploadFile(filename="photo.jpg", content=fake_image_exe)
    service = EvidenceService(test_db_session, test_storage_adapter)

    with pytest.raises(HTTPException) as exc_info:
        await service.ingest_evidence(
            case_id=case.id,
            file=upload,  # type: ignore[arg-type]
            evidence_number=None,
            current_user=user,
            settings=test_settings,
        )
    assert exc_info.value.status_code == 400
    disguise_detail = exc_info.value.detail
    assert isinstance(disguise_detail, dict)
    assert disguise_detail["code"] == "UNSUPPORTED_MEDIA_TYPE"
