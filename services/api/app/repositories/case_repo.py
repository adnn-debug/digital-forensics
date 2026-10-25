"""Case repository implementation."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.case import Case, CaseStatus
from app.repositories.base import BaseRepository
from app.schemas.case import CaseCreate, CaseUpdate


class CaseRepository(BaseRepository[Case]):
    """Data access repository for Forensic Case entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Case)

    async def get_by_case_number(self, case_number: str) -> Case | None:
        """Find a case by unique case number (e.g. CAS-2026-0091)."""
        stmt = (
            select(Case)
            .where(Case.case_number == case_number.strip().upper())
            .options(
                selectinload(Case.lead_investigator),
                selectinload(Case.evidence_items),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_details(self, case_id: UUID) -> Case | None:
        """Retrieve a case with loaded evidence items and investigator."""
        stmt = (
            select(Case)
            .where(Case.id == case_id)
            .options(
                selectinload(Case.lead_investigator),
                selectinload(Case.evidence_items),
                selectinload(Case.reports),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_status(
        self,
        status: CaseStatus = CaseStatus.ACTIVE,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Case]:
        """List cases filtered by lifecycle status."""
        stmt = (
            select(Case)
            .where(Case.status == status.value)
            .order_by(Case.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create_case(self, payload: CaseCreate) -> Case:
        """Create and persist a new forensic investigation case."""
        case = Case(
            case_number=payload.case_number.strip().upper(),
            title=payload.title,
            description=payload.description,
            status=payload.status.value,
            lead_investigator_id=payload.lead_investigator_id,
        )
        return await self.add(case)

    async def update_case(self, case: Case, payload: CaseUpdate) -> Case:
        """Update case metadata and status."""
        if payload.title is not None:
            case.title = payload.title
        if payload.description is not None:
            case.description = payload.description
        if payload.status is not None:
            case.status = payload.status.value
        if payload.lead_investigator_id is not None:
            case.lead_investigator_id = payload.lead_investigator_id
        await self.session.flush()
        return case
