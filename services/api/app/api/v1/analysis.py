"""Forensic analysis jobs, status polling, and execution history API endpoints."""

from __future__ import annotations

import logging
import math
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, FlexibleUser, get_db, get_storage_adapter, require_roles
from app.db.models.analysis import AnalysisArtifact, AnalysisStatus
from app.db.models.user import UserRole
from app.queue.service import AnalysisJobService
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.evidence_repo import EvidenceRepository
from app.schemas.analysis import (
    AnalysisJobCreateResponse,
    ForensicAnalysisCreate,
    ForensicAnalysisRead,
)
from app.schemas.pagination import PaginatedResponse
from app.storage.local import LocalFilesystemStorageAdapter

logger = logging.getLogger("ps05.api.analysis")

router = APIRouter(prefix="/analysis", tags=["Forensic Analysis & Tasks"])


@router.post(
    "/jobs",
    response_model=AnalysisJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Schedule a durable background forensic analysis job",
    dependencies=[require_roles(UserRole.ADMIN.value, UserRole.EXAMINER.value)],
)
async def create_analysis_job(
    payload: ForensicAnalysisCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_idempotency_key: Annotated[str | None, Header()] = None,
) -> AnalysisJobCreateResponse:
    """
    Enqueue an asynchronous forensic task.
    Returns immediately with job and analysis IDs.
    Supports idempotency protection via payload or X-Idempotency-Key header.
    """
    evidence_repo = EvidenceRepository(db)
    evidence = await evidence_repo.get(payload.evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "EVIDENCE_NOT_FOUND",
                "message": f"Evidence item {payload.evidence_id} not found.",
            },
        )

    # Use header or payload idempotency key
    effective_idempotency_key = payload.idempotency_key or x_idempotency_key

    service = AnalysisJobService(db)
    analysis, was_created = await service.enqueue_analysis(
        evidence_id=payload.evidence_id,
        analysis_type=payload.analysis_type,
        parameters=payload.parameters,
        examiner_notes=payload.examiner_notes,
        idempotency_key=effective_idempotency_key,
        max_retries=payload.max_retries,
        timeout_seconds=payload.timeout_seconds,
        initiated_by_id=current_user.id,
    )

    msg = (
        "Analysis job successfully queued for execution"
        if was_created
        else "Idempotent request: returning existing job record"
    )

    return AnalysisJobCreateResponse(
        job_id=analysis.job_id or str(analysis.id),
        analysis_id=analysis.id,
        evidence_id=analysis.evidence_id,
        analysis_type=analysis.analysis_type,
        status=AnalysisStatus(analysis.status),
        message=msg,
        created_at=analysis.created_at,
    )


@router.get(
    "/jobs/{job_id_or_analysis_id}",
    response_model=ForensicAnalysisRead,
    summary="Poll status, progress, timestamps, and findings of an analysis job",
)
async def get_job_status(
    job_id_or_analysis_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ForensicAnalysisRead:
    """
    Retrieve authoritative status from PostgreSQL.
    Accepts either an analysis UUID or transport RQ job ID string.
    """
    service = AnalysisJobService(db)
    analysis = await service.get_job_status(job_id_or_analysis_id)

    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ANALYSIS_JOB_NOT_FOUND",
                "message": f"Job or analysis record '{job_id_or_analysis_id}' was not found.",
            },
        )

    return ForensicAnalysisRead.model_validate(analysis)


@router.get(
    "/history",
    response_model=PaginatedResponse[ForensicAnalysisRead],
    summary="Retrieve paginated analysis job execution history with filtering",
)
async def get_analysis_history(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    case_id: Annotated[UUID | None, Query(description="Filter by case ID")] = None,
    evidence_id: Annotated[UUID | None, Query(description="Filter by evidence ID")] = None,
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            description="Filter by status (QUEUED, PROCESSING, COMPLETED, FAILED, SKIPPED)",
        ),
    ] = None,
    analysis_type: Annotated[str | None, Query(description="Filter by analysis heuristic")] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> PaginatedResponse[ForensicAnalysisRead]:
    """Query chronological analysis job history with multi-attribute filtering."""
    repo = AnalysisRepository(db)
    offset = (page - 1) * page_size

    items, total = await repo.list_history(
        evidence_id=evidence_id,
        case_id=case_id,
        status=status_filter,
        analysis_type=analysis_type,
        limit=page_size,
        offset=offset,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedResponse[ForensicAnalysisRead](
        items=[ForensicAnalysisRead.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=total_pages,
    )


@router.post(
    "/jobs/{analysis_id}/retry",
    response_model=AnalysisJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually re-enqueue a failed or interrupted forensic analysis task",
    dependencies=[require_roles(UserRole.ADMIN.value, UserRole.EXAMINER.value)],
)
async def retry_analysis_job(
    analysis_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisJobCreateResponse:
    """Re-enqueue a previously failed or terminated job."""
    service = AnalysisJobService(db)
    try:
        analysis = await service.retry_job(analysis_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ANALYSIS_NOT_FOUND", "message": str(exc)},
        ) from exc

    return AnalysisJobCreateResponse(
        job_id=analysis.job_id or str(analysis.id),
        analysis_id=analysis.id,
        evidence_id=analysis.evidence_id,
        analysis_type=analysis.analysis_type,
        status=AnalysisStatus(analysis.status),
        message="Job successfully re-enqueued for execution",
        created_at=analysis.created_at,
    )


@router.get(
    "/artifacts/{artifact_id}/content",
    summary="Stream derivative forensic artifact (e.g. ELA heatmap PNG) directly from storage vault",
)
async def get_artifact_content(
    artifact_id: UUID,
    current_user: FlexibleUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """Retrieve and stream an analysis artifact with original MIME type and read-only protection."""
    stmt = select(AnalysisArtifact).where(AnalysisArtifact.id == artifact_id)
    result = await db.execute(stmt)
    artifact = result.scalar_one_or_none()

    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ARTIFACT_NOT_FOUND", "message": f"Artifact '{artifact_id}' was not found."},
        )

    physical_path = adapter.get_local_path_readonly(artifact.storage_path)
    return FileResponse(
        path=str(physical_path),
        media_type=artifact.mime_type,
        filename=artifact.file_name,
    )
