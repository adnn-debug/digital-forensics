"""
Forensic metadata extraction orchestration service.

Coordinates ExifTool and FFprobe adapters, persists structured extracts to PostgreSQL,
and appends immutable chain-of-custody audit trail records.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageException
from app.core.security import compute_event_hash
from app.db.models.audit import AuditEvent, AuditEventType
from app.db.models.evidence import EvidenceItem, MetadataExtract
from app.forensics.base import ToolExecutionResult
from app.forensics.exif_adapter import ExifToolAdapter
from app.forensics.ffprobe_adapter import FFprobeAdapter
from app.repositories.evidence_repo import EvidenceRepository
from app.schemas.evidence import MetadataExtractCreate
from app.storage.local import LocalFilesystemStorageAdapter

logger = logging.getLogger("ps05.forensics.service")


class MetadataExtractionService:
    """Service orchestrating multi-tool forensic extraction and database persistence."""

    def __init__(
        self,
        db: AsyncSession,
        adapter: LocalFilesystemStorageAdapter,
        *,
        exif_adapter: ExifToolAdapter | None = None,
        ffprobe_adapter: FFprobeAdapter | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.settings = settings or get_settings()
        self.evidence_repo = EvidenceRepository(db)

        self.exif_adapter = exif_adapter or ExifToolAdapter(
            binary_path=self.settings.EXIFTOOL_PATH,
            timeout_seconds=self.settings.FORENSIC_SUBPROCESS_TIMEOUT_SECONDS,
        )
        self.ffprobe_adapter = ffprobe_adapter or FFprobeAdapter(
            binary_path=self.settings.FFPROBE_PATH,
            timeout_seconds=self.settings.FORENSIC_SUBPROCESS_TIMEOUT_SECONDS,
        )

    async def extract_and_persist(
        self,
        evidence: EvidenceItem,
        current_user_id: UUID | None = None,
    ) -> list[MetadataExtract]:
        """
        Extract container and stream metadata using ExifTool and FFprobe, then persist to DB.

        Modality Routing:
        - IMAGE: ExifTool for deep EXIF/IPTC/XMP/MakerNotes; FFprobe for container/format check.
        - AUDIO: FFprobe for container & audio streams; ExifTool for ID3/RIFF/Vorbis tags.
        - VIDEO: FFprobe for container & video/audio stream profiles; ExifTool for container atom tags.
        """
        # Resolve physical storage path securely
        physical_path = self.adapter.get_local_path_readonly(evidence.storage_path)
        if not physical_path.is_file():
            raise StorageException(f"Evidence physical file not found at: {physical_path}")


        results: list[ToolExecutionResult] = []

        # 1. Execute ExifTool
        try:
            exif_res = self.exif_adapter.extract_metadata(physical_path)
            results.append(exif_res)
        except Exception as exc:
            logger.exception("Unexpected error running ExifTool adapter: %s", exc)

        # 2. Execute FFprobe
        try:
            ffprobe_res = self.ffprobe_adapter.extract_metadata(physical_path)
            results.append(ffprobe_res)
        except Exception as exc:
            logger.exception("Unexpected error running FFprobe adapter: %s", exc)

        persisted_extracts: list[MetadataExtract] = []
        now = datetime.now(UTC)

        for res in results:
            payload = MetadataExtractCreate(
                evidence_id=evidence.id,
                tool_name=res.tool_name,
                tool_version=res.tool_version,
                raw_metadata=res.raw_metadata,
                filtered_forensic_metadata=res.filtered_forensic_metadata,
            )
            extract = await self.evidence_repo.create_metadata_extract(payload)
            persisted_extracts.append(extract)

        # 3. Append immutable chain-of-custody AuditEvent
        tools_summary = ", ".join(f"{r.tool_name} (v{r.tool_version})" for r in results)
        action_desc = (
            f"Forensic technical metadata extracted for evidence '{evidence.evidence_number}' "
            f"using {tools_summary}."
        )

        event_hash = compute_event_hash(
            event_type=AuditEventType.METADATA_EXTRACTED.value,
            action_description=action_desc,
            user_id=str(current_user_id) if current_user_id else "SYSTEM",
            case_id=str(evidence.case_id),
            previous_hash=None,
            timestamp=now.isoformat(),
        )

        audit_event = AuditEvent(
            case_id=evidence.case_id,
            evidence_id=evidence.id,
            user_id=current_user_id,
            event_type=AuditEventType.METADATA_EXTRACTED.value,
            action_description=action_desc,
            previous_state_hash=None,
            event_hash=event_hash,
            payload_delta={
                "tools_executed": [
                    {
                        "tool": r.tool_name,
                        "version": r.tool_version,
                        "success": r.success,
                        "duration_ms": r.execution_duration_ms,
                        "errors": r.errors,
                    }
                    for r in results
                ],
            },
            timestamp=now,
        )
        self.db.add(audit_event)
        await self.db.flush()

        logger.info(
            "Persisted %d metadata extracts for evidence %s (%s)",
            len(persisted_extracts),
            evidence.evidence_number,
            evidence.id,
        )
        return persisted_extracts

    async def get_evidence_extracts(self, evidence_id: UUID) -> list[MetadataExtract]:
        """Query all persisted metadata extracts for a given evidence item."""
        stmt = (
            select(MetadataExtract)
            .where(MetadataExtract.evidence_id == evidence_id)
            .order_by(MetadataExtract.extracted_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
