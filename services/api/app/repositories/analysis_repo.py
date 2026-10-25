from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.analysis import AnalysisArtifact, AnalysisStatus, ForensicAnalysis
from app.db.models.evidence import EvidenceItem
from app.repositories.base import BaseRepository
from app.schemas.analysis import (
    AnalysisArtifactCreate,
    ForensicAnalysisCreate,
    ForensicAnalysisUpdate,
)


class AnalysisRepository(BaseRepository[ForensicAnalysis]):
    """Data access repository for forensic analyses and artifacts."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ForensicAnalysis)

    async def get_with_artifacts_and_findings(self, analysis_id: UUID) -> ForensicAnalysis | None:
        """Fetch an analysis job with eager-loaded artifacts and findings."""
        stmt = (
            select(ForensicAnalysis)
            .where(ForensicAnalysis.id == analysis_id)
            .options(
                selectinload(ForensicAnalysis.artifacts),
                selectinload(ForensicAnalysis.findings),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_job_id(self, job_id: str) -> ForensicAnalysis | None:
        """Fetch analysis by its transport queue job ID."""
        stmt = (
            select(ForensicAnalysis)
            .where(ForensicAnalysis.job_id == job_id)
            .options(
                selectinload(ForensicAnalysis.artifacts),
                selectinload(ForensicAnalysis.findings),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> ForensicAnalysis | None:
        """Fetch analysis by examiner-provided idempotency key."""
        stmt = (
            select(ForensicAnalysis)
            .where(ForensicAnalysis.idempotency_key == idempotency_key)
            .options(
                selectinload(ForensicAnalysis.artifacts),
                selectinload(ForensicAnalysis.findings),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active_by_evidence_and_type(
        self, evidence_id: UUID, analysis_type: str
    ) -> ForensicAnalysis | None:
        """Find an existing active job (QUEUED or PROCESSING) for the same evidence and type."""
        stmt = (
            select(ForensicAnalysis)
            .where(
                ForensicAnalysis.evidence_id == evidence_id,
                ForensicAnalysis.analysis_type == analysis_type,
                ForensicAnalysis.status.in_(
                    [AnalysisStatus.QUEUED.value, AnalysisStatus.PROCESSING.value]
                ),
            )
            .order_by(ForensicAnalysis.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_interrupted_jobs(self, heartbeat_cutoff: datetime) -> Sequence[ForensicAnalysis]:
        """
        Locate tasks left in PROCESSING whose last heartbeat or start time
        is older than the crash detection threshold.
        """
        stmt = select(ForensicAnalysis).where(
            ForensicAnalysis.status == AnalysisStatus.PROCESSING.value,
            (
                (
                    ForensicAnalysis.last_heartbeat_at.is_not(None)
                    & (ForensicAnalysis.last_heartbeat_at < heartbeat_cutoff)
                )
                | (
                    ForensicAnalysis.last_heartbeat_at.is_(None)
                    & (ForensicAnalysis.started_at < heartbeat_cutoff)
                )
            ),
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_evidence(self, evidence_id: UUID) -> Sequence[ForensicAnalysis]:
        """List all analyses conducted on a specific evidence item."""
        stmt = (
            select(ForensicAnalysis)
            .where(ForensicAnalysis.evidence_id == evidence_id)
            .options(
                selectinload(ForensicAnalysis.artifacts),
                selectinload(ForensicAnalysis.findings),
            )
            .order_by(ForensicAnalysis.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_history(
        self,
        evidence_id: UUID | None = None,
        case_id: UUID | None = None,
        status: str | None = None,
        analysis_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[ForensicAnalysis], int]:
        """Paginated analysis history query with multi-attribute filtering."""
        query = select(ForensicAnalysis).options(
            selectinload(ForensicAnalysis.artifacts),
            selectinload(ForensicAnalysis.findings),
        )
        count_query = select(func.count(ForensicAnalysis.id))

        if case_id is not None:
            query = query.join(EvidenceItem, ForensicAnalysis.evidence_id == EvidenceItem.id).where(
                EvidenceItem.case_id == case_id
            )
            count_query = count_query.join(
                EvidenceItem, ForensicAnalysis.evidence_id == EvidenceItem.id
            ).where(EvidenceItem.case_id == case_id)

        if evidence_id is not None:
            query = query.where(ForensicAnalysis.evidence_id == evidence_id)
            count_query = count_query.where(ForensicAnalysis.evidence_id == evidence_id)

        if status is not None:
            query = query.where(ForensicAnalysis.status == status)
            count_query = count_query.where(ForensicAnalysis.status == status)

        if analysis_type is not None:
            query = query.where(ForensicAnalysis.analysis_type == analysis_type)
            count_query = count_query.where(ForensicAnalysis.analysis_type == analysis_type)

        query = query.order_by(ForensicAnalysis.created_at.desc()).limit(limit).offset(offset)

        total_res = await self.session.execute(count_query)
        total = int(total_res.scalar_one() or 0)

        items_res = await self.session.execute(query)
        items = items_res.scalars().all()

        return items, total

    async def create_analysis(self, payload: ForensicAnalysisCreate) -> ForensicAnalysis:
        """Register a pending forensic analysis task."""
        analysis_type_val = (
            payload.analysis_type.value
            if hasattr(payload.analysis_type, "value")
            else str(payload.analysis_type)
        )
        analysis = ForensicAnalysis(
            evidence_id=payload.evidence_id,
            analysis_type=analysis_type_val,
            parameters=payload.parameters,
            examiner_notes=payload.examiner_notes,
            initiated_by_id=payload.initiated_by_id,
            idempotency_key=payload.idempotency_key,
            max_retries=payload.max_retries,
            timeout_seconds=payload.timeout_seconds,
            status=AnalysisStatus.QUEUED.value,
        )
        return await self.add(analysis)

    async def update_analysis(
        self,
        analysis: ForensicAnalysis,
        payload: ForensicAnalysisUpdate,
    ) -> ForensicAnalysis:
        """Update job lifecycle status, summary findings, and error messages."""
        if payload.status is not None:
            analysis.status = (
                payload.status.value if hasattr(payload.status, "value") else str(payload.status)
            )
        if payload.job_id is not None:
            analysis.job_id = payload.job_id
        if payload.attempt_count is not None:
            analysis.attempt_count = payload.attempt_count
        if payload.error_code is not None:
            analysis.error_code = payload.error_code
        if payload.summary_results is not None:
            analysis.summary_results = payload.summary_results
        if payload.examiner_notes is not None:
            analysis.examiner_notes = payload.examiner_notes
        if payload.error_message is not None:
            analysis.error_message = payload.error_message
        if payload.worker_id is not None:
            analysis.worker_id = payload.worker_id
        if payload.started_at is not None:
            analysis.started_at = payload.started_at
        if payload.last_heartbeat_at is not None:
            analysis.last_heartbeat_at = payload.last_heartbeat_at
        if payload.completed_at is not None:
            analysis.completed_at = payload.completed_at
        await self.session.flush()
        return analysis

    async def create_artifact(self, payload: AnalysisArtifactCreate) -> AnalysisArtifact:
        """Store a derivative artifact reference (e.g. ELA heatmap, spectrogram PNG)."""
        artifact = AnalysisArtifact(
            analysis_id=payload.analysis_id,
            artifact_type=payload.artifact_type.value,
            storage_path=payload.storage_path,
            file_name=payload.file_name,
            mime_type=payload.mime_type,
            file_size_bytes=payload.file_size_bytes,
            hash_sha256=payload.hash_sha256.lower(),
            artifact_metadata=payload.artifact_metadata,
        )
        self.session.add(artifact)
        await self.session.flush()
        return artifact
