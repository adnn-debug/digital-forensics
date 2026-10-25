"""
Cryptographic re-verification service for evidence integrity and tamper detection.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import StorageException
from app.core.security import compute_event_hash
from app.db.models.audit import AuditEvent, AuditEventType
from app.db.models.evidence import EvidenceItem, HashVerification, VerificationTrigger
from app.db.models.user import User
from app.repositories.case_repo import CaseRepository
from app.schemas.evidence import HashVerificationResult
from app.services.evidence_service import EvidenceService
from app.storage.local import LocalFilesystemStorageAdapter

logger = logging.getLogger("ps05.services.verification")


class VerificationService:
    """Service verifying cryptographic hash baselines and detecting evidence bit-rot or tampering."""

    def __init__(self, db: AsyncSession, adapter: LocalFilesystemStorageAdapter) -> None:
        self.db = db
        self.adapter = adapter
        self.case_repo = CaseRepository(db)

    async def verify_evidence_integrity(
        self,
        *,
        case_id: UUID,
        evidence_id: UUID,
        trigger: VerificationTrigger,
        current_user: User,
    ) -> HashVerificationResult:
        """
        Independently verify cryptographic baseline integrity against the physical vault.

        Reads the stored file directly from the private storage vault in bounded chunks,
        calculates SHA-256 over the actual stored bytes, and compares the result
        against the expected SHA-256 registered at intake.

        Audit Disclosure:
        Verification confirms that the stored byte stream exactly matches the reference
        SHA-256 baseline established at intake (bit-level integrity). It does NOT prove
        that the evidence was authentic, unmodified, or trustworthy prior to intake.
        """
        case = await self.case_repo.get_by_id(case_id)
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CASE_NOT_FOUND", "message": f"Case with ID '{case_id}' was not found."},
            )

        EvidenceService.assert_case_access(case, current_user)

        stmt = select(EvidenceItem).where(
            EvidenceItem.id == evidence_id,
            EvidenceItem.case_id == case_id,
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

        # Stream stored bytes from private storage in 64KB bounded chunks
        hasher = hashlib.sha256()
        try:
            async for chunk in self.adapter.read_stream(evidence.storage_path, chunk_size=65536):
                hasher.update(chunk)
        except StorageException as sexc:
            logger.error("Failed to read evidence bytes for verification: %s", sexc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "STORAGE_READ_FAILED",
                    "message": f"Failed to read physical evidence bytes from vault: {sexc}",
                },
            ) from sexc

        calculated_sha256 = hasher.hexdigest().lower()
        expected_sha256 = evidence.primary_hash_sha256.lower()
        is_intact = (calculated_sha256 == expected_sha256)

        now = datetime.now(UTC)

        # Persist HashVerification audit row
        verification = HashVerification(
            evidence_id=evidence.id,
            calculated_sha256=calculated_sha256,
            expected_sha256=expected_sha256,
            is_intact=is_intact,
            verification_trigger=trigger.value,
            verified_by_id=current_user.id,
            verified_at=now,
        )
        self.db.add(verification)

        # Append AuditEvent for verification or tamper detection
        event_type = (
            AuditEventType.HASH_VERIFIED.value if is_intact else AuditEventType.TAMPER_DETECTED.value
        )
        action_desc = (
            f"Cryptographic hash re-verification PASSED for '{evidence.evidence_number}' (sha256: {calculated_sha256})"
            if is_intact
            else (
                f"CRITICAL: Cryptographic hash mismatch for '{evidence.evidence_number}'! "
                f"Expected: {expected_sha256}, Actual: {calculated_sha256}"
            )
        )

        event_hash = compute_event_hash(
            event_type=event_type,
            action_description=action_desc,
            user_id=str(current_user.id),
            case_id=str(case.id),
            previous_hash=None,
            timestamp=now.isoformat(),
        )
        audit_event = AuditEvent(
            case_id=case.id,
            evidence_id=evidence.id,
            user_id=current_user.id,
            event_type=event_type,
            action_description=action_desc,
            previous_state_hash=None,
            event_hash=event_hash,
            payload_delta={
                "expected_sha256": expected_sha256,
                "calculated_sha256": calculated_sha256,
                "is_intact": is_intact,
                "trigger": trigger.value,
            },
            timestamp=now,
        )
        self.db.add(audit_event)

        await self.db.commit()

        if not is_intact:
            logger.critical(
                "EVIDENCE TAMPER DETECTED: Evidence %s has sha256=%s, expected=%s",
                evidence.id,
                calculated_sha256,
                expected_sha256,
            )

        return HashVerificationResult(
            evidence_id=evidence.id,
            evidence_number=evidence.evidence_number,
            is_intact=is_intact,
            expected_sha256=expected_sha256,
            calculated_sha256=calculated_sha256,
            verification_trigger=trigger.value,
            verified_at=now,
        )
