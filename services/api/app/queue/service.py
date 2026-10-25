"""Forensic Analysis Job Service: Enqueuing, Idempotency, and Crash Recovery."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from rq import Retry
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analysis import AnalysisStatus, AnalysisType, ForensicAnalysis
from app.queue.connection import get_redis_sync_client
from app.queue.queue import FORENSIC_QUEUE_NAME, get_queue
from app.queue.tasks import run_analysis_job
from app.repositories.analysis_repo import AnalysisRepository
from app.schemas.analysis import ForensicAnalysisCreate

logger = logging.getLogger("ps05.queue.service")


class AnalysisJobService:
    """Orchestrates durable background job enqueuing, idempotency guards, and crash recovery."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AnalysisRepository(session)

    async def enqueue_analysis(
        self,
        evidence_id: UUID,
        analysis_type: AnalysisType | str,
        parameters: dict[str, Any] | None = None,
        examiner_notes: str | None = None,
        idempotency_key: str | None = None,
        max_retries: int = 3,
        timeout_seconds: int = 300,
        initiated_by_id: UUID | None = None,
        queue_connection: Any | None = None,
    ) -> tuple[ForensicAnalysis, bool]:
        """
        Register a forensic analysis job in PostgreSQL and dispatch to the Redis RQ queue.
        Enforces idempotency protection: returns existing job if identical job is in progress.
        Returns: (analysis_record, was_created_and_enqueued)
        """
        type_str = analysis_type.value if hasattr(analysis_type, "value") else str(analysis_type)

        # 1. Idempotency Check via explicit idempotency key
        if idempotency_key:
            existing = await self.repo.get_by_idempotency_key(idempotency_key)
            if existing:
                logger.info(
                    "Idempotency hit for key '%s': returning existing job %s (status=%s)",
                    idempotency_key,
                    existing.id,
                    existing.status,
                )
                return existing, False

        # 2. Duplicate In-Flight Protection: Check if job is already active for this evidence
        active_job = await self.repo.find_active_by_evidence_and_type(evidence_id, type_str)
        if active_job:
            logger.info(
                "Active job already running for evidence %s and type %s: returning existing job %s",
                evidence_id,
                type_str,
                active_job.id,
            )
            return active_job, False

        # 3. Create authoritative job record in PostgreSQL with QUEUED state
        payload = ForensicAnalysisCreate(
            evidence_id=evidence_id,
            analysis_type=AnalysisType(type_str)
            if type_str in AnalysisType._value2member_map_
            else AnalysisType.TEST_ANALYSIS,
            parameters=parameters,
            examiner_notes=examiner_notes,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            initiated_by_id=initiated_by_id,
        )
        analysis = await self.repo.create_analysis(payload)
        await self.session.commit()

        # 4. Enqueue into Redis RQ with bounded retries and timeout
        try:
            conn = queue_connection or get_redis_sync_client()
            q = get_queue(name=FORENSIC_QUEUE_NAME, connection=conn)

            rq_job = q.enqueue(
                run_analysis_job,
                str(analysis.id),
                job_timeout=timeout_seconds,
                retry=Retry(max=max_retries, interval=[2, 5, 10]),
            )

            # Persist RQ transport job ID into PostgreSQL
            analysis.job_id = rq_job.id
            await self.session.commit()
            logger.info(
                "Enqueued job %s (RQ ID: %s) for evidence %s", analysis.id, rq_job.id, evidence_id
            )
            return analysis, True

        except Exception as exc:
            logger.error("Failed to enqueue job %s into Redis: %s", analysis.id, exc)
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_code = "REDIS_ENQUEUE_ERROR"
            analysis.error_message = f"Failed to enqueue into message broker: {exc}"
            await self.session.commit()
            raise

    async def get_job_status(self, job_or_analysis_id: str) -> ForensicAnalysis | None:
        """Fetch authoritative job status from PostgreSQL by analysis UUID or RQ job ID."""
        try:
            analysis_uuid = UUID(job_or_analysis_id)
            analysis = await self.repo.get_with_artifacts_and_findings(analysis_uuid)
            if analysis:
                return analysis
        except ValueError:
            pass

        return await self.repo.get_by_job_id(job_or_analysis_id)

    async def recover_interrupted_jobs(
        self,
        heartbeat_timeout_seconds: int = 60,
        queue_connection: Any | None = None,
    ) -> list[ForensicAnalysis]:
        """
        Crash recovery watchdog:
        Identifies jobs left in PROCESSING state after worker termination or timeout.
        If attempts remain under max_retries, re-enqueues for processing.
        Otherwise marks as FAILED with WORKER_CRASHED error code.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=heartbeat_timeout_seconds)
        interrupted = await self.repo.find_interrupted_jobs(cutoff)
        recovered: list[ForensicAnalysis] = []

        if not interrupted:
            return recovered

        logger.warning(
            "Crash recovery detected %d interrupted jobs stuck in PROCESSING.", len(interrupted)
        )
        conn = queue_connection or get_redis_sync_client()
        q = get_queue(name=FORENSIC_QUEUE_NAME, connection=conn)

        for job in interrupted:
            current_attempts = job.attempt_count or 0
            if current_attempts < job.max_retries:
                job.status = AnalysisStatus.QUEUED.value
                job.error_code = "WORKER_CRASHED_RECOVERED"
                job.error_message = (
                    f"Recovered from crashed worker missing heartbeat at {job.last_heartbeat_at}"
                )
                job.last_heartbeat_at = datetime.now(UTC)

                # Re-enqueue into RQ
                rq_job = q.enqueue(
                    run_analysis_job,
                    str(job.id),
                    job_timeout=job.timeout_seconds,
                    retry=Retry(max=job.max_retries, interval=[2, 5, 10]),
                )
                job.job_id = rq_job.id
                logger.info("Re-enqueued interrupted job %s (New RQ ID: %s)", job.id, rq_job.id)
            else:
                job.status = AnalysisStatus.FAILED.value
                job.error_code = "WORKER_CRASHED"
                job.error_message = (
                    f"Worker died while processing and exceeded maximum retries ({job.max_retries})"
                )
                job.completed_at = datetime.now(UTC)
                logger.error("Interrupted job %s marked FAILED due to exhausted retries.", job.id)

            recovered.append(job)

        await self.session.commit()
        return recovered

    async def retry_job(
        self,
        analysis_id: UUID,
        queue_connection: Any | None = None,
    ) -> ForensicAnalysis:
        """Manually re-enqueue a failed or interrupted job."""
        analysis = await self.repo.get(analysis_id)
        if analysis is None:
            raise ValueError(f"Analysis record {analysis_id} not found")

        analysis.status = AnalysisStatus.QUEUED.value
        analysis.error_code = None
        analysis.error_message = None
        analysis.completed_at = None

        conn = queue_connection or get_redis_sync_client()
        q = get_queue(name=FORENSIC_QUEUE_NAME, connection=conn)

        rq_job = q.enqueue(
            run_analysis_job,
            str(analysis.id),
            job_timeout=analysis.timeout_seconds,
            retry=Retry(max=analysis.max_retries, interval=[2, 5, 10]),
        )
        analysis.job_id = rq_job.id
        await self.session.commit()
        return analysis
