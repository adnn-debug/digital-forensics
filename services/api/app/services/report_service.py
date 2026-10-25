"""
Courtroom Forensic Examination Report domain service.

Coordinates case data aggregation, cryptographic report compilation,
storage in the read-only reports vault, and immutable chain-of-custody logging.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    ResourceNotFoundException,
    SecurityViolationException,
)
from app.core.security import compute_event_hash
from app.db.models.audit import AuditEvent, AuditEventType
from app.db.models.case import Case
from app.db.models.evidence import EvidenceItem
from app.db.models.report import Report
from app.db.models.user import User, UserRole
from app.reports.builder import (
    CourtroomReportBuilder,
    CourtroomReportData,
    ReportAnalysisData,
    ReportArtifactData,
    ReportAuditEventData,
    ReportEvidenceItemData,
    ReportFindingData,
)
from app.repositories.case_repo import CaseRepository
from app.repositories.report_repo import ReportRepository
from app.schemas.report import ReportCreate, ReportGenerateRequest
from app.storage.hasher import MultiHasher
from app.storage.local import LocalFilesystemStorageAdapter

logger = logging.getLogger("ps05.services.report_service")


class ReportService:
    """Service managing courtroom PDF generation and archival."""

    def __init__(
        self,
        db: AsyncSession,
        adapter: LocalFilesystemStorageAdapter,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.settings = settings or get_settings()
        self.case_repo = CaseRepository(db)
        self.report_repo = ReportRepository(db)

    def _check_case_access(self, case: Case, current_user: User) -> None:
        """Enforce role-based access control for case reports."""
        if current_user.role == UserRole.ADMIN.value:
            return
        if case.lead_investigator_id == current_user.id:
            return
        raise SecurityViolationException(
            f"User {current_user.email} is not authorized to access case {case.case_number}"
        )

    async def generate_report(
        self,
        case_id: UUID,
        current_user: User,
        payload: ReportGenerateRequest,
    ) -> Report:
        """
        Aggregate case records, compile Platypus PDF, lock in reports vault, and log audit event.
        """
        if current_user.role not in (UserRole.ADMIN.value, UserRole.EXAMINER.value):
            raise SecurityViolationException("Viewer role is not authorized to generate sealed forensic reports.")

        case = await self.case_repo.get(case_id)
        if case is None:
            raise ResourceNotFoundException("Case", str(case_id))
        self._check_case_access(case, current_user)

        # 1. Fetch Evidence Items
        stmt = (
            select(EvidenceItem)
            .where(EvidenceItem.case_id == case_id)
            .options(
                selectinload(EvidenceItem.hash_verifications),
                selectinload(EvidenceItem.forensic_analyses),
            )
            .order_by(EvidenceItem.ingested_at.asc())
        )
        ev_result = await self.db.execute(stmt)
        all_evidence = list(ev_result.scalars().all())

        if payload.included_evidence_ids:
            target_ids = {str(eid) for eid in payload.included_evidence_ids}
            evidence_items = [e for e in all_evidence if str(e.id) in target_ids]
        else:
            evidence_items = all_evidence

        # Transform Evidence Items
        report_evidence: list[ReportEvidenceItemData] = []
        for e in evidence_items:
            # Check latest hash verification if present
            is_intact = True
            if e.hash_verifications:
                sorted_vers = sorted(e.hash_verifications, key=lambda v: v.verified_at, reverse=True)
                is_intact = sorted_vers[0].is_intact

            report_evidence.append(
                ReportEvidenceItemData(
                    evidence_number=e.evidence_number,
                    original_filename=e.original_filename,
                    media_type=e.media_type,
                    file_size_bytes=e.file_size_bytes,
                    primary_hash_sha256=e.primary_hash_sha256,
                    hash_md5=e.hash_md5,
                    hash_sha1=e.hash_sha1,
                    ingested_at=e.ingested_at.isoformat(),
                    is_intact=is_intact,
                )
            )

        # 2. Fetch Audit Events for Chronological Chain of Custody
        audit_stmt = (
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .options(selectinload(AuditEvent.user))
            .order_by(AuditEvent.timestamp.asc())
        )
        audit_res = await self.db.execute(audit_stmt)
        raw_audits = list(audit_res.scalars().all())

        report_audits: list[ReportAuditEventData] = [
            ReportAuditEventData(
                timestamp=a.timestamp.isoformat(),
                user_name=a.user.full_name if a.user else "SYSTEM",
                event_type=a.event_type,
                action_description=a.action_description,
                event_hash=a.event_hash,
            )
            for a in raw_audits
        ]

        # 3. Fetch Forensic Analyses with Findings and Artifacts
        from app.db.models.analysis import ForensicAnalysis
        analysis_stmt = (
            select(ForensicAnalysis)
            .where(ForensicAnalysis.evidence_id.in_([e.id for e in evidence_items]))
            .options(
                selectinload(ForensicAnalysis.findings),
                selectinload(ForensicAnalysis.artifacts),
            )
            .order_by(ForensicAnalysis.created_at.asc())
        )
        analysis_res = await self.db.execute(analysis_stmt)
        raw_analyses = list(analysis_res.scalars().all())

        report_analyses: list[ReportAnalysisData] = []
        for an in raw_analyses:
            # Build findings
            findings_data = [
                ReportFindingData(
                    finding_type=f.finding_type,
                    severity=f.severity,
                    title=f.title,
                    description=f.description,
                    confidence_score=f.confidence_score,
                )
                for f in an.findings
            ]

            # Build artifacts
            artifacts_data: list[ReportArtifactData] = []
            for art in an.artifacts:
                art_bytes: bytes | None = None
                try:
                    art_bytes = self.adapter.read(art.storage_path)
                except Exception as ex:
                    logger.warning("Could not read artifact %s from vault: %s", art.storage_path, ex)

                artifacts_data.append(
                    ReportArtifactData(
                        artifact_type=art.artifact_type,
                        file_name=art.file_name,
                        hash_sha256=art.hash_sha256,
                        image_bytes=art_bytes,
                    )
                )

            report_analyses.append(
                ReportAnalysisData(
                    analysis_type=an.analysis_type,
                    status=an.status,
                    completed_at=an.completed_at.isoformat() if an.completed_at else an.created_at.isoformat(),
                    summary_results=an.summary_results or {},
                    findings=findings_data,
                    artifacts=artifacts_data,
                )
            )

        # 4. Generate Unique Report Number and Timestamp
        now_dt = datetime.now(UTC)
        now_iso = now_dt.isoformat()
        rand_suffix = uuid4().hex[:6].upper()
        report_number = f"REP-{case.case_number}-{rand_suffix}"
        verification_token = uuid4().hex

        # 5. Assemble Courtroom Data & Build PDF
        report_data = CourtroomReportData(
            case_number=case.case_number,
            case_title=case.title,
            case_description=case.description,
            opened_at=case.created_at.isoformat(),
            examiner_name=current_user.full_name,
            examiner_role=current_user.role,
            examiner_email=current_user.email,
            report_number=report_number,
            report_title=payload.title,
            generated_at=now_iso,
            evidence_items=report_evidence,
            audit_events=report_audits,
            analyses=report_analyses,
            examiner_certification=payload.examiner_certification,
            jurisdiction=payload.jurisdiction,
            court_name=payload.court_name,
            docket_number=payload.docket_number,
            classification_marking=payload.classification_marking,
            verification_url=(
                f"{self.settings.FRONTEND_URL.rstrip('/')}/reports/verify"
                f"?token={verification_token}"
            ),
        )

        builder = CourtroomReportBuilder()
        pdf_bytes = builder.build_pdf(report_data)

        # 6. Cryptographic Baseline & Vault Archival
        hasher = MultiHasher()
        pdf_digests = hasher.hash_bytes(pdf_bytes)

        storage_key = self.adapter.generate_key(
            category="reports",
            case_id=case_id,
            filename=f"{report_number}.pdf",
        )
        self.adapter.write(storage_key, pdf_bytes)
        self.adapter.lock_readonly(storage_key)

        # 7. Persist Database Record
        report_create = ReportCreate(
            case_id=case_id,
            report_number=report_number,
            title=payload.title,
            examiner_certification=payload.examiner_certification,
            jurisdiction=payload.jurisdiction,
            court_name=payload.court_name,
            docket_number=payload.docket_number,
            classification_marking=payload.classification_marking,
            verification_token=verification_token,
            generated_by_id=current_user.id,
            storage_path=storage_key,
            file_hash_sha256=pdf_digests.sha256,
            file_size_bytes=pdf_digests.byte_count,
            included_evidence_ids=[str(e.id) for e in evidence_items],
        )
        report = await self.report_repo.create_report(report_create)

        # 8. Append Immutable Audit Event
        action_desc = (
            f"Courtroom examination report '{report_number}' generated and sealed with SHA-256: {pdf_digests.sha256}."
        )
        event_hash = compute_event_hash(
            event_type=AuditEventType.REPORT_GENERATED.value,
            action_description=action_desc,
            user_id=str(current_user.id),
            case_id=str(case_id),
            previous_hash=raw_audits[-1].event_hash if raw_audits else None,
            timestamp=now_iso,
        )

        audit_event = AuditEvent(
            case_id=case_id,
            user_id=current_user.id,
            event_type=AuditEventType.REPORT_GENERATED.value,
            action_description=action_desc,
            previous_state_hash=raw_audits[-1].event_hash if raw_audits else None,
            event_hash=event_hash,
            payload_delta={
                "report_id": str(report.id),
                "report_number": report.report_number,
                "file_hash_sha256": pdf_digests.sha256,
                "file_size_bytes": pdf_digests.byte_count,
                "evidence_count": len(evidence_items),
            },
            timestamp=now_dt,
        )
        self.db.add(audit_event)
        await self.db.commit()

        logger.info(
            "Sealed courtroom report %s (SHA-256: %s) archived in vault.",
            report_number,
            pdf_digests.sha256,
        )
        return report

    async def list_case_reports(self, case_id: UUID, current_user: User) -> Sequence[Report]:
        """List all compiled reports for a given case."""
        case = await self.case_repo.get(case_id)
        if case is None:
            raise ResourceNotFoundException("Case", str(case_id))
        self._check_case_access(case, current_user)
        return await self.report_repo.list_by_case(case_id)

    async def get_report_by_id(self, case_id: UUID, report_id: UUID, current_user: User) -> Report:
        """Fetch report record by ID."""
        case = await self.case_repo.get(case_id)
        if case is None:
            raise ResourceNotFoundException("Case", str(case_id))
        self._check_case_access(case, current_user)

        report = await self.report_repo.get(report_id)
        if report is None or report.case_id != case_id:
            raise ResourceNotFoundException("Report", str(report_id))
        return report

    async def get_report_pdf_bytes(
        self, case_id: UUID, report_id: UUID, current_user: User
    ) -> tuple[bytes, str]:
        """Retrieve physical sealed PDF bytes for download."""
        report = await self.get_report_by_id(case_id, report_id, current_user)
        pdf_bytes = self.adapter.read(report.storage_path)
        filename = f"{report.report_number}.pdf"
        return pdf_bytes, filename
