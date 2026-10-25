"""
Evidence intake, upload streaming, and independent integrity verification API endpoints.

Security & Forensic Guarantees:
- Scoped to an authorized case (examiner owns case, or admin/auditor).
- Stream uploads to private storage using bounded memory and configurable file-size limits.
- Validates file signatures (magic bytes) for IMAGE, AUDIO, and VIDEO.
- Rejects empty, unsupported, mismatched, or oversized files before/during stream.
- Sanitizes display filenames and blocks path traversal attempts.
- Server-side generated evidence IDs and structured storage keys.
- Preserves exact uploaded byte stream without alteration.
- Calculates SHA-256, MD5, and SHA-1 over actual stored bytes.
- Atomic two-phase commit: interrupted uploads or DB failures never become falsely successful records.
- Independent cryptographic hash verification with legal integrity vs. authenticity disclosure.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, FlexibleUser, get_db, get_storage_adapter, require_roles
from app.core.config import Settings, get_settings
from app.db.models.evidence import VerificationTrigger
from app.db.models.user import UserRole
from app.schemas.evidence import (
    EvidenceDetailRead,
    EvidenceItemRead,
    EvidenceUploadResponse,
    HashVerificationResult,
    MetadataExtractRead,
)
from app.services.evidence_service import EvidenceService
from app.services.verification_service import VerificationService
from app.storage.local import LocalFilesystemStorageAdapter

logger = logging.getLogger("ps05.evidence")

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["Evidence Intake & Verification"])


@router.post(
    "/upload",
    response_model=EvidenceUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Secure evidence intake stream for images, audio, and video",
    dependencies=[require_roles(UserRole.ADMIN.value, UserRole.EXAMINER.value)],
)
async def upload_evidence(
    case_id: UUID,
    file: UploadFile = File(..., description="Evidence bitstream file (image, audio, or video)"),
    evidence_number: str | None = Query(
        default=None,
        description="Optional custom evidence number; auto-generated if omitted",
    ),
    current_user: CurrentUser = None,  # type: ignore[assignment]
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> Any:
    """
    Ingest a new evidence file into the specified case vault.

    - Verifies case existence and investigator authorization.
    - Streams payload to private temporary staging using bounded memory (64KB chunks).
    - Enforces configurable maximum upload size limit.
    - Inspects file signature (magic bytes) to strictly validate IMAGE, AUDIO, or VIDEO media types.
    - Rejects empty, unsupported, executable, or mismatched files.
    - Computes SHA-256, MD5, and SHA-1 over the exact byte stream written to disk.
    - Persists EvidenceItem and baseline HashVerification in PostgreSQL atomically.
    - Automatically purges staging files if the upload is aborted or an error occurs.
    """
    evidence_service = EvidenceService(db, adapter)
    evidence_item = await evidence_service.ingest_evidence(
        case_id=case_id,
        file=file,
        evidence_number=evidence_number,
        current_user=current_user,
        settings=settings,
    )
    return EvidenceUploadResponse.model_validate(evidence_item)


@router.get(
    "",
    response_model=list[EvidenceItemRead],
    summary="List all evidence items registered in an authorized case",
)
async def list_case_evidence(
    case_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """List all evidence bitstreams ingested into a given case."""
    evidence_service = EvidenceService(db, adapter)
    items = await evidence_service.list_by_case(case_id, current_user)
    return [EvidenceItemRead.model_validate(i) for i in items]


@router.get(
    "/{evidence_id}",
    response_model=EvidenceDetailRead,
    summary="Get full details of an evidence item including metadata extracts and hash history",
)
async def get_evidence_item(
    case_id: UUID,
    evidence_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """Retrieve full details of an evidence record."""
    evidence_service = EvidenceService(db, adapter)
    evidence = await evidence_service.get_by_id(case_id, evidence_id, current_user)
    return EvidenceDetailRead.model_validate(evidence)


@router.get(
    "/{evidence_id}/metadata",
    response_model=list[MetadataExtractRead],
    summary="Get technical and stream metadata extracts for an evidence item",
)
async def get_evidence_metadata(
    case_id: UUID,
    evidence_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """Retrieve all ExifTool and FFprobe metadata extracts for an evidence bitstream."""
    evidence_service = EvidenceService(db, adapter)
    evidence = await evidence_service.get_by_id(case_id, evidence_id, current_user)
    from app.forensics.metadata_service import MetadataExtractionService
    meta_service = MetadataExtractionService(db, adapter)
    extracts = await meta_service.get_evidence_extracts(evidence.id)
    return [MetadataExtractRead.model_validate(e) for e in extracts]


@router.post(
    "/{evidence_id}/metadata/extract",
    response_model=list[MetadataExtractRead],
    summary="Trigger on-demand technical metadata extraction using ExifTool and FFprobe",
    dependencies=[require_roles(UserRole.ADMIN.value, UserRole.EXAMINER.value)],
)
async def trigger_evidence_metadata_extraction(
    case_id: UUID,
    evidence_id: UUID,
    current_user: CurrentUser = None,  # type: ignore[assignment]
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> Any:
    """
    Execute sandboxed ExifTool and FFprobe extraction on vault bitstream,
    persist results, and record an immutable audit event.
    """
    evidence_service = EvidenceService(db, adapter)
    evidence = await evidence_service.get_by_id(case_id, evidence_id, current_user)
    from app.forensics.metadata_service import MetadataExtractionService
    meta_service = MetadataExtractionService(db, adapter, settings=settings)
    extracts = await meta_service.extract_and_persist(evidence, current_user.id)
    await db.commit()
    return [MetadataExtractRead.model_validate(e) for e in extracts]


@router.post(
    "/{evidence_id}/verify-hash",
    response_model=HashVerificationResult,
    summary="Independently re-calculate SHA-256 over stored bytes and verify integrity",
)
async def verify_evidence_hash(
    case_id: UUID,
    evidence_id: UUID,
    trigger: VerificationTrigger = Query(
        default=VerificationTrigger.MANUAL,
        description="Trigger reason for verification audit",
    ),
    current_user: CurrentUser = None,  # type: ignore[assignment]
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)] = None,  # type: ignore[assignment]
) -> Any:
    """
    Independently verify cryptographic baseline integrity.

    Reads the stored file directly from the private storage vault in bounded chunks,
    calculates SHA-256 over the actual stored bytes, and compares the result
    against the expected SHA-256 registered at intake.

    Audit Disclosure:
    Verification confirms that the stored byte stream exactly matches the reference
    SHA-256 baseline established at intake (bit-level integrity). It does NOT prove
    that the evidence was authentic, unmodified, or trustworthy prior to intake.
    """
    verification_service = VerificationService(db, adapter)
    return await verification_service.verify_evidence_integrity(
        case_id=case_id,
        evidence_id=evidence_id,
        trigger=trigger,
        current_user=current_user,
    )


@router.get(
    "/{evidence_id}/content",
    summary="Stream raw evidentiary bitstream for preview or download",
)
async def get_evidence_content(
    case_id: UUID,
    evidence_id: UUID,
    current_user: FlexibleUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """Stream stored evidence file with original MIME type and read-only protection."""
    evidence_service = EvidenceService(db, adapter)
    evidence = await evidence_service.get_by_id(case_id, evidence_id, current_user)
    physical_path = adapter.get_local_path_readonly(evidence.storage_path)
    return FileResponse(
        path=str(physical_path),
        media_type=evidence.mime_type,
        filename=evidence.original_filename,
    )
