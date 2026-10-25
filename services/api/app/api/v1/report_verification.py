"""Public verification endpoint for sealed report QR codes.

The endpoint exposes only minimal report metadata and a byte-level hash check.
Access is gated by a high-entropy token embedded in the generated report QR code.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_storage_adapter
from app.db.models.report import Report
from app.storage.local import LocalFilesystemStorageAdapter

router = APIRouter(prefix="/reports", tags=["Public Report Verification"])


class PublicReportVerification(BaseModel):
    """Minimal public response for validating a report QR code."""

    report_number: str
    title: str
    created_at: datetime
    expected_sha256: str
    actual_sha256: str | None
    file_size_bytes: int
    integrity_valid: bool
    message: str


@router.get(
    "/verify",
    response_model=PublicReportVerification,
    summary="Verify the integrity of a sealed report using its QR token",
)
async def verify_public_report(
    token: Annotated[str, Query(min_length=32, max_length=64)],
    db: Annotated[AsyncSession, Depends(get_db)],
    adapter: Annotated[LocalFilesystemStorageAdapter, Depends(get_storage_adapter)],
) -> Any:
    """Re-hash the archived PDF and compare it with the baseline stored at generation."""
    result = await db.execute(select(Report).where(Report.verification_token == token))
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPORT_NOT_FOUND", "message": "No report matches this verification token."},
        )

    try:
        pdf_bytes = adapter.read(report.storage_path)
    except Exception:
        return PublicReportVerification(
            report_number=report.report_number,
            title=report.title,
            created_at=report.created_at,
            expected_sha256=report.file_hash_sha256,
            actual_sha256=None,
            file_size_bytes=report.file_size_bytes,
            integrity_valid=False,
            message="The archived PDF could not be read; integrity could not be verified.",
        )

    actual_hash = hashlib.sha256(pdf_bytes).hexdigest()
    integrity_valid = actual_hash == report.file_hash_sha256
    return PublicReportVerification(
        report_number=report.report_number,
        title=report.title,
        created_at=report.created_at,
        expected_sha256=report.file_hash_sha256,
        actual_sha256=actual_hash,
        file_size_bytes=len(pdf_bytes),
        integrity_valid=integrity_valid,
        message=(
            "The archived PDF matches its recorded SHA-256 baseline."
            if integrity_valid
            else "The archived PDF does not match its recorded SHA-256 baseline."
        ),
    )
