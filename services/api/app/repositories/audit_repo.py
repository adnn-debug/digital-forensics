"""Audit repository implementation for append-only chain of custody."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent, AuditEventType
from app.repositories.base import BaseRepository
from app.schemas.audit import AuditEventCreate


class AuditRepository(BaseRepository[AuditEvent]):
    """Append-only repository for chain-of-custody audit logging."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditEvent)

    async def get_latest_event_for_case(self, case_id: UUID) -> AuditEvent | None:
        """Retrieve the most recent audit event in a case."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.timestamp.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_event(self) -> AuditEvent | None:
        """Retrieve the most recent event across the audit log."""
        stmt = select(AuditEvent).order_by(AuditEvent.timestamp.desc(), AuditEvent.id.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_auth_event(self) -> AuditEvent | None:
        """Retrieve the latest LOGIN/LOGOUT event in the separate authentication audit chain."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.event_type.in_([AuditEventType.LOGIN.value, AuditEventType.LOGOUT.value]))
            .order_by(AuditEvent.timestamp.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_case(self, case_id: UUID, limit: int = 200) -> Sequence[AuditEvent]:
        """List chain-of-custody events in chronological sequence."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_evidence(self, evidence_id: UUID, limit: int = 100) -> Sequence[AuditEvent]:
        """List chain-of-custody events concerning an evidence item."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.evidence_id == evidence_id)
            .order_by(AuditEvent.timestamp.asc(), AuditEvent.id.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def append_event(self, payload: AuditEventCreate) -> AuditEvent:
        """Append an audit entry; the caller must provide its hash-chain metadata."""
        event = AuditEvent(
            case_id=payload.case_id,
            evidence_id=payload.evidence_id,
            user_id=payload.user_id,
            event_type=payload.event_type.value,
            action_description=payload.action_description,
            ip_address=payload.ip_address,
            user_agent=payload.user_agent,
            previous_state_hash=payload.previous_state_hash,
            event_hash=payload.event_hash.lower(),
            payload_delta=payload.payload_delta,
            timestamp=payload.timestamp or datetime.now(UTC),
        )
        return await self.add(event)
