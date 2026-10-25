"""Report repository implementation."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.report import Report
from app.repositories.base import BaseRepository
from app.schemas.report import ReportCreate


class ReportRepository(BaseRepository[Report]):
    """Data access repository for courtroom examination reports."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Report)

    async def get_by_report_number(self, report_number: str) -> Report | None:
        """Find a sealed report by its unique report identifier."""
        stmt = (
            select(Report)
            .where(Report.report_number == report_number.strip().upper())
            .options(
                selectinload(Report.case),
                selectinload(Report.generated_by),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_case(self, case_id: UUID) -> Sequence[Report]:
        """List all compiled reports associated with an investigation case."""
        stmt = (
            select(Report)
            .where(Report.case_id == case_id)
            .order_by(Report.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_report(self, payload: ReportCreate) -> Report:
        """Persist courtroom examination report metadata."""
        report = Report(
            case_id=payload.case_id,
            report_number=payload.report_number.strip().upper(),
            title=payload.title,
            examiner_certification=payload.examiner_certification,
            jurisdiction=payload.jurisdiction,
            court_name=payload.court_name,
            docket_number=payload.docket_number,
            classification_marking=payload.classification_marking,
            verification_token=payload.verification_token,
            generated_by_id=payload.generated_by_id,
            storage_path=payload.storage_path,
            file_hash_sha256=payload.file_hash_sha256.lower(),
            file_size_bytes=payload.file_size_bytes,
            included_evidence_ids=payload.included_evidence_ids,
        )
        return await self.add(report)
