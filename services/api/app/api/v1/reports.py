"""Courtroom Forensic Examination Reports API endpoints."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, FlexibleUser, get_db, get_storage_adapter, require_roles
from app.db.models.user import UserRole
from app.schemas.report import ReportGenerateRequest, ReportRead
from app.services.report_service import ReportService
from app.storage.local import LocalFilesystemStorageAdapter

router = APIRouter(prefix="/cases/{case_id}/reports", tags=["Courtroom Reports"])


@router.post(
    "/generate",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a courtroom-admissible sealed PDF examination report",
    dependencies=[require_roles(UserRole.ADMIN.value, UserRole.EXAMINER.value)],
)
async def generate_courtroom_report(
    case_id: UUID,
    payload: ReportGenerateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """
    Compile a complete, courtroom-admissible digital forensics report.

    Aggregates case metadata, examiner certification, baseline evidence hashes,
    chronological chain of custody, and forensic analysis exhibits (heatmaps, spectrograms, keyframes).
    Locks the generated PDF in the read-only reports vault with an immutable audit event.
    """
    service = ReportService(db, adapter)
    report = await service.generate_report(case_id, current_user, payload)
    return ReportRead.model_validate(report)


@router.get(
    "",
    response_model=list[ReportRead],
    summary="List all sealed examination reports for a case",
)
async def list_case_reports(
    case_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """Retrieve all reports generated for the specified case."""
    service = ReportService(db, adapter)
    reports = await service.list_case_reports(case_id, current_user)
    return [ReportRead.model_validate(r) for r in reports]


@router.get(
    "/{report_id}",
    response_model=ReportRead,
    summary="Get metadata for a specific courtroom report",
)
async def get_report_metadata(
    case_id: UUID,
    report_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """Retrieve metadata and hash information for a specific sealed report."""
    service = ReportService(db, adapter)
    report = await service.get_report_by_id(case_id, report_id, current_user)
    return ReportRead.model_validate(report)


@router.get(
    "/{report_id}/download",
    summary="Download the sealed courtroom PDF report",
)
async def download_report_pdf(
    case_id: UUID,
    report_id: UUID,
    current_user: FlexibleUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """Download the byte-exact sealed PDF report file from the reports vault."""
    service = ReportService(db, adapter)
    pdf_bytes, filename = await service.get_report_pdf_bytes(case_id, report_id, current_user)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
