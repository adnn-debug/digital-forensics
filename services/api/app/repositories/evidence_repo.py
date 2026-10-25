"""Evidence repository implementation."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.evidence import EvidenceItem, HashVerification, MetadataExtract
from app.repositories.base import BaseRepository
from app.schemas.evidence import (
    EvidenceItemCreate,
    HashVerificationCreate,
    MetadataExtractCreate,
)


class EvidenceRepository(BaseRepository[EvidenceItem]):
    """Data access repository for digital evidence items and verifications."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EvidenceItem)

    async def get_by_case_and_number(self, case_id: UUID, evidence_number: str) -> EvidenceItem | None:
        """Find an evidence item within a specific case by its evidence identifier."""
        stmt = (
            select(EvidenceItem)
            .where(
                EvidenceItem.case_id == case_id,
                EvidenceItem.evidence_number == evidence_number.strip(),
            )
            .options(
                selectinload(EvidenceItem.hash_verifications),
                selectinload(EvidenceItem.metadata_extracts),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_relations(self, evidence_id: UUID) -> EvidenceItem | None:
        """Fetch an evidence item by ID eagerly loading metadata extracts and hash verifications."""
        stmt = (
            select(EvidenceItem)
            .where(EvidenceItem.id == evidence_id)
            .options(
                selectinload(EvidenceItem.metadata_extracts),
                selectinload(EvidenceItem.hash_verifications),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_metadata_extracts(self, evidence_id: UUID) -> Sequence[MetadataExtract]:
        """Fetch all metadata extracts associated with an evidence item."""
        stmt = (
            select(MetadataExtract)
            .where(MetadataExtract.evidence_id == evidence_id)
            .order_by(MetadataExtract.extracted_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_sha256(self, sha256_hash: str) -> Sequence[EvidenceItem]:
        """Query evidence items sharing an identical primary SHA-256 hash."""
        stmt = select(EvidenceItem).where(
            EvidenceItem.primary_hash_sha256 == sha256_hash.strip().lower()
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_case(self, case_id: UUID) -> Sequence[EvidenceItem]:
        """List all evidence bitstreams ingested into a given case."""
        stmt = (
            select(EvidenceItem)
            .where(EvidenceItem.case_id == case_id)
            .order_by(EvidenceItem.ingested_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_evidence(self, payload: EvidenceItemCreate) -> EvidenceItem:
        """Register newly ingested evidence metadata in the database."""
        item = EvidenceItem(
            case_id=payload.case_id,
            evidence_number=payload.evidence_number.strip(),
            original_filename=payload.original_filename,
            stored_filename=payload.stored_filename,
            mime_type=payload.mime_type,
            media_type=payload.media_type.value,
            file_size_bytes=payload.file_size_bytes,
            primary_hash_sha256=payload.primary_hash_sha256.lower(),
            hash_md5=payload.hash_md5.lower(),
            hash_sha1=payload.hash_sha1.lower(),
            storage_path=payload.storage_path,
            is_quarantined=payload.is_quarantined,
            uploaded_by_id=payload.uploaded_by_id,
        )
        return await self.add(item)

    async def create_hash_verification(self, payload: HashVerificationCreate) -> HashVerification:
        """Log a cryptographic re-verification baseline check."""
        verification = HashVerification(
            evidence_id=payload.evidence_id,
            calculated_sha256=payload.calculated_sha256.lower(),
            expected_sha256=payload.expected_sha256.lower(),
            is_intact=payload.is_intact,
            verification_trigger=payload.verification_trigger.value,
            verified_by_id=payload.verified_by_id,
        )
        self.session.add(verification)
        await self.session.flush()
        return verification

    async def create_metadata_extract(self, payload: MetadataExtractCreate) -> MetadataExtract:
        """Persist structured output from ExifTool or FFprobe."""
        extract = MetadataExtract(
            evidence_id=payload.evidence_id,
            tool_name=payload.tool_name,
            tool_version=payload.tool_version,
            raw_metadata=payload.raw_metadata,
            filtered_forensic_metadata=payload.filtered_forensic_metadata,
        )
        self.session.add(extract)
        await self.session.flush()
        return extract
