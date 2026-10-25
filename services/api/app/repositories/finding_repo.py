"""Finding repository implementation."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.finding import Finding
from app.repositories.base import BaseRepository
from app.schemas.finding import FindingCreate, FindingUpdate


class FindingRepository(BaseRepository[Finding]):
    """Data access repository for forensic findings and anomaly observations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Finding)

    async def list_by_analysis(self, analysis_id: UUID) -> Sequence[Finding]:
        """List all findings identified by a specific analysis job."""
        stmt = (
            select(Finding)
            .where(Finding.analysis_id == analysis_id)
            .order_by(Finding.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_evidence(self, evidence_id: UUID) -> Sequence[Finding]:
        """List all findings across any analyses executed for an evidence item."""
        stmt = (
            select(Finding)
            .where(Finding.evidence_id == evidence_id)
            .order_by(Finding.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_finding(self, payload: FindingCreate) -> Finding:
        """Persist a new evidentiary finding."""
        finding = Finding(
            analysis_id=payload.analysis_id,
            evidence_id=payload.evidence_id,
            finding_type=payload.finding_type.value,
            severity=payload.severity.value,
            title=payload.title,
            description=payload.description,
            confidence_score=payload.confidence_score,
            evidence_offset=payload.evidence_offset,
            finding_metadata=payload.finding_metadata,
        )
        return await self.add(finding)

    async def update_finding(self, finding: Finding, payload: FindingUpdate) -> Finding:
        """Update finding severity, notes, or confidence."""
        if payload.severity is not None:
            finding.severity = payload.severity.value
        if payload.title is not None:
            finding.title = payload.title
        if payload.description is not None:
            finding.description = payload.description
        if payload.confidence_score is not None:
            finding.confidence_score = payload.confidence_score
        if payload.evidence_offset is not None:
            finding.evidence_offset = payload.evidence_offset
        if payload.finding_metadata is not None:
            finding.finding_metadata = payload.finding_metadata
        await self.session.flush()
        return finding

    async def clear_findings_for_analysis(self, analysis_id: UUID) -> int:
        """Atomically remove existing findings for an analysis prior to re-execution."""
        stmt = delete(Finding).where(Finding.analysis_id == analysis_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        count = getattr(result, "rowcount", 0)
        return int(count or 0)
