"""
Evidence ingestion service implementing secure intake, verification, and audit chaining.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.exceptions import StorageException
from app.core.file_validator import HEADER_READ_LENGTH, detect_media_signature
from app.core.security import compute_event_hash
from app.db.models.audit import AuditEvent, AuditEventType
from app.db.models.case import Case
from app.db.models.evidence import EvidenceItem, HashVerification, VerificationTrigger
from app.db.models.user import User, UserRole
from app.repositories.audit_repo import AuditRepository
from app.repositories.case_repo import CaseRepository
from app.repositories.evidence_repo import EvidenceRepository
from app.storage.local import LocalFilesystemStorageAdapter
from app.storage.manager import StorageManager
from app.storage.transaction import StagedStorageTransaction

logger = logging.getLogger("ps05.services.evidence")


class EvidenceService:
    """Service orchestrating evidence intake, vault storage, and audit chaining."""

    def __init__(self, db: AsyncSession, adapter: LocalFilesystemStorageAdapter) -> None:
        self.db = db
        self.adapter = adapter
        self.case_repo = CaseRepository(db)
        self.evidence_repo = EvidenceRepository(db)

    @staticmethod
    def assert_case_access(case: Case, current_user: User) -> None:
        """Enforce case-level authorization for evidence actions."""
        if current_user.role in (UserRole.ADMIN.value, UserRole.AUDITOR.value):
            return  # Full organization-wide audit access

        if case.lead_investigator_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "CASE_ACCESS_DENIED",
                    "message": "You are not authorized to access or modify evidence for this case.",
                },
            )

    async def get_authorized_case(self, case_id: UUID, current_user: User) -> Case:
        """Retrieve case and ensure the current user has access."""
        case = await self.case_repo.get_by_id(case_id)
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CASE_NOT_FOUND", "message": f"Case with ID '{case_id}' was not found."},
            )
        self.assert_case_access(case, current_user)
        return case

    async def ingest_evidence(
        self,
        *,
        case_id: UUID,
        file: UploadFile,
        evidence_number: str | None,
        current_user: User,
        settings: Settings,
    ) -> EvidenceItem:
        """
        Ingest a digital evidence file into the case vault.

        Enforces:
        - Case existence and investigator authorization.
        - Magic bytes signature detection (IMAGE, AUDIO, VIDEO).
        - Rejection of empty, unsupported, or disguised executables.
        - Path traversal mitigation on filename.
        - Atomic two-phase storage transaction.
        - Concurrent SHA-256, MD5, and SHA-1 hashing.
        - Duplicate detection warning/logging.
        - Read-only permission locking on vault promotion.
        - Baseline hash verification and immutable audit trail emission.
        """
        case = await self.get_authorized_case(case_id, current_user)

        # 1. Sanitize original filename and protect against path traversal
        raw_filename = file.filename or "evidence_file"
        safe_display_name = StorageManager.sanitize_filename(raw_filename)
        if not safe_display_name:
            safe_display_name = f"evidence_{uuid4().hex[:8]}"

        # 2. Inspect initial header bytes for magic signature validation
        header_chunk = await file.read(HEADER_READ_LENGTH)
        if not header_chunk or len(header_chunk) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "EMPTY_FILE",
                    "message": "The uploaded evidence file is empty (0 bytes). Intake rejected.",
                },
            )

        media_type, detected_mime = detect_media_signature(header_chunk)

        # 3. Server-side generated identifiers and storage key
        evidence_id = uuid4()
        if not evidence_number or not evidence_number.strip():
            evidence_number = f"EVD-{case.case_number}-{evidence_id.hex[:6].upper()}"
        else:
            evidence_number = evidence_number.strip()

        storage_key = self.adapter.generate_key(
            category="originals",
            case_id=case.id,
            filename=safe_display_name,
            prefix=evidence_id.hex[:12],
        )

        max_size = settings.STORAGE_MAX_UPLOAD_SIZE_BYTES

        # 4. Stream to temporary staging file inside atomic two-phase storage transaction
        try:
            with StagedStorageTransaction(self.adapter) as txn:
                try:
                    meta, md5_hash, sha1_hash = await txn.stage_stream(
                        key=storage_key,
                        stream=file,
                        initial_chunk=header_chunk,
                        max_size_bytes=max_size,
                        chunk_size=65536,
                    )
                except StorageException as sexc:
                    if "exceeds maximum limit" in str(sexc):
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail={
                                "code": "FILE_TOO_LARGE",
                                "message": (
                                    f"Uploaded file exceeds maximum limit of {max_size} bytes "
                                    f"({max_size // (1024 * 1024)} MB)."
                                ),
                            },
                        ) from sexc
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"code": "STORAGE_ERROR", "message": str(sexc)},
                    ) from sexc

                # Check for existing duplicate evidence within the case
                dup_stmt = select(EvidenceItem).where(
                    EvidenceItem.case_id == case.id,
                    EvidenceItem.primary_hash_sha256 == meta.hash_sha256,
                )
                dup_result = await self.db.execute(dup_stmt)
                existing_dup = dup_result.scalar_one_or_none()
                if existing_dup:
                    logger.warning(
                        "Duplicate evidence bitstream detected in case %s: matching %s (sha256: %s)",
                        case.case_number,
                        existing_dup.evidence_number,
                        meta.hash_sha256,
                    )

                # 5. Persist evidence record in PostgreSQL
                now = datetime.now(UTC)
                evidence_item = EvidenceItem(
                    id=evidence_id,
                    case_id=case.id,
                    evidence_number=evidence_number,
                    original_filename=safe_display_name,
                    stored_filename=Path(storage_key).name,
                    mime_type=detected_mime,
                    media_type=media_type.value,
                    file_size_bytes=meta.file_size_bytes,
                    primary_hash_sha256=meta.hash_sha256,
                    hash_md5=md5_hash,
                    hash_sha1=sha1_hash,
                    storage_path=storage_key,
                    is_quarantined=False,
                    uploaded_by_id=current_user.id,
                    ingested_at=now,
                )
                self.db.add(evidence_item)

                # 6. Record baseline HashVerification record
                verification = HashVerification(
                    evidence_id=evidence_id,
                    calculated_sha256=meta.hash_sha256,
                    expected_sha256=meta.hash_sha256,
                    is_intact=True,
                    verification_trigger=VerificationTrigger.MANUAL.value,
                    verified_by_id=current_user.id,
                    verified_at=now,
                )
                self.db.add(verification)

                # 7. Append immutable AuditEvent for chain of custody
                audit_ts = now.isoformat()
                action_desc = (
                    f"Evidence '{evidence_number}' ({media_type.value}, {meta.file_size_bytes} bytes, "
                    f"sha256:{meta.hash_sha256[:12]}...) ingested into case '{case.case_number}' by {current_user.email}"
                )
                latest_audit = await AuditRepository(self.db).get_latest_event_for_case(case.id)
                previous_hash = latest_audit.event_hash if latest_audit else None
                event_hash = compute_event_hash(
                    event_type=AuditEventType.EVIDENCE_INGESTED.value,
                    action_description=action_desc,
                    user_id=str(current_user.id),
                    case_id=str(case.id),
                    previous_hash=previous_hash,
                    timestamp=audit_ts,
                )
                audit_event = AuditEvent(
                    case_id=case.id,
                    evidence_id=evidence_id,
                    user_id=current_user.id,
                    event_type=AuditEventType.EVIDENCE_INGESTED.value,
                    action_description=action_desc,
                    previous_state_hash=previous_hash,
                    event_hash=event_hash,
                    payload_delta={
                        "evidence_number": evidence_number,
                        "media_type": media_type.value,
                        "mime_type": detected_mime,
                        "file_size_bytes": meta.file_size_bytes,
                        "sha256": meta.hash_sha256,
                        "is_duplicate": existing_dup is not None,
                    },
                    timestamp=now,
                )
                self.db.add(audit_event)

                # Commit DB changes
                await self.db.commit()
                await self.db.refresh(evidence_item)

                # Promote staging file from tmp to permanent vault with read-only lock
                txn.commit()

                logger.info(
                    "Secure evidence intake complete: ID=%s No=%s Size=%d SHA256=%s",
                    evidence_id,
                    evidence_number,
                    meta.file_size_bytes,
                    meta.hash_sha256,
                )

                # Automatic post-intake metadata extraction (ExifTool & FFprobe)
                try:
                    from app.forensics.metadata_service import MetadataExtractionService
                    meta_svc = MetadataExtractionService(self.db, self.adapter, settings=settings)
                    await meta_svc.extract_and_persist(evidence_item, current_user.id)
                    await self.db.commit()
                except Exception as meta_exc:
                    logger.warning("Post-intake forensic metadata extraction failed: %s", meta_exc)

                return evidence_item

        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Upload processing error: %s", exc)
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "UPLOAD_PROCESSING_FAILED",
                    "message": f"Failed to ingest evidence: {exc}",
                },
            ) from exc

    async def list_by_case(self, case_id: UUID, current_user: User) -> list[EvidenceItem]:
        """List all evidence bitstreams ingested into a given case."""
        await self.get_authorized_case(case_id, current_user)
        items = await self.evidence_repo.list_by_case(case_id)
        return list(items)

    async def get_by_id(self, case_id: UUID, evidence_id: UUID, current_user: User) -> EvidenceItem:
        """Retrieve full details of an evidence record with metadata extracts and verifications."""
        await self.get_authorized_case(case_id, current_user)
        stmt = (
            select(EvidenceItem)
            .where(
                EvidenceItem.id == evidence_id,
                EvidenceItem.case_id == case_id,
            )
            .options(
                selectinload(EvidenceItem.metadata_extracts),
                selectinload(EvidenceItem.hash_verifications),
            )
        )
        result = await self.db.execute(stmt)
        evidence = result.scalar_one_or_none()
        if not evidence:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "EVIDENCE_NOT_FOUND",
                    "message": f"Evidence item '{evidence_id}' was not found in case '{case_id}'.",
                },
            )
        return evidence
