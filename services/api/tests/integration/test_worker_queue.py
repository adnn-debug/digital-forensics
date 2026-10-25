"""Integration tests for durable background queue, worker execution, idempotency, and crash recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from rq.worker import SimpleWorker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.models.analysis import AnalysisStatus, AnalysisType
from app.db.models.case import Case, CaseStatus
from app.db.models.evidence import EvidenceItem, MediaType
from app.db.models.user import User, UserRole
from app.queue.queue import FORENSIC_QUEUE_NAME, get_queue
from app.queue.service import AnalysisJobService
from app.queue.tasks import run_analysis_job
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.finding_repo import FindingRepository
from app.schemas.analysis import ForensicAnalysisCreate


async def _create_test_environment(db: AsyncSession) -> tuple[User, Case, EvidenceItem]:
    """Helper to seed user, case, and evidence item in PostgreSQL/SQLite test DB."""
    user = User(
        email=f"examiner_{uuid4().hex[:8]}@forensics.agency.gov",
        hashed_password="dummy_hashed_password",
        full_name="Lead Forensic Examiner",
        role=UserRole.EXAMINER.value,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    case = Case(
        case_number=f"CASE-{uuid4().hex[:6].upper()}",
        title="Durable Worker Verification Case",
        description="Testing Redis queue durability and PostgreSQL state mirroring",
        status=CaseStatus.ACTIVE.value,
        lead_investigator_id=user.id,
    )
    db.add(case)
    await db.flush()

    evidence = EvidenceItem(
        case_id=case.id,
        evidence_number=f"EVD-{uuid4().hex[:6].upper()}",
        original_filename="sample_evidence.jpg",
        stored_filename=f"{uuid4().hex}.jpg",
        mime_type="image/jpeg",
        media_type=MediaType.IMAGE.value,
        file_size_bytes=1024,
        primary_hash_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        hash_md5="d41d8cd98f00b204e9800998ecf8427e",
        hash_sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        storage_path="originals/sample_evidence.jpg",
        is_quarantined=False,
        uploaded_by_id=user.id,
    )
    db.add(evidence)
    await db.commit()

    return user, case, evidence


@pytest.mark.asyncio
async def test_queue_execution_and_worker_completion(
    test_db_session: AsyncSession,
    fake_sync_redis: Any,
) -> None:
    """Verify task is registered in PostgreSQL, enqueued in Redis, and executed by worker."""
    user, case, evidence = await _create_test_environment(test_db_session)

    service = AnalysisJobService(test_db_session)
    analysis, enqueued = await service.enqueue_analysis(
        evidence_id=evidence.id,
        analysis_type=AnalysisType.TEST_ANALYSIS,
        parameters={"test_key": "test_value"},
        initiated_by_id=user.id,
        queue_connection=fake_sync_redis,
    )

    assert enqueued is True
    assert analysis.status == AnalysisStatus.QUEUED.value
    assert analysis.job_id is not None
    assert analysis.attempt_count == 0

    # Execute with worker in burst mode
    q = get_queue(name=FORENSIC_QUEUE_NAME, connection=fake_sync_redis)
    worker = SimpleWorker([q], connection=fake_sync_redis)
    worker.work(burst=True)

    # Refresh and verify PostgreSQL state
    await test_db_session.refresh(analysis)
    analysis_repo = AnalysisRepository(test_db_session)
    updated = await analysis_repo.get_with_artifacts_and_findings(analysis.id)
    assert updated is not None
    assert updated.status == AnalysisStatus.COMPLETED.value
    assert updated.attempt_count == 1
    assert updated.completed_at is not None
    assert updated.summary_results is not None
    assert updated.summary_results.get("test_status") == "PASSED"
    assert len(updated.findings) == 1
    assert "Evidentiary Baseline Validated" in updated.findings[0].title


@pytest.mark.asyncio
async def test_job_polling_and_api_lifecycle(
    async_client: AsyncClient,
    test_db_session: AsyncSession,
    fake_sync_redis: Any,
) -> None:
    """Verify HTTP API job dispatch, polling transitions, and history retrieval."""
    user, case, evidence = await _create_test_environment(test_db_session)
    token = create_access_token(user.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Enqueue job via API
    create_payload = {
        "evidence_id": str(evidence.id),
        "analysis_type": "TEST_ANALYSIS",
        "parameters": {"examiner": "Agent Smith"},
    }
    resp = await async_client.post("/api/v1/analysis/jobs", json=create_payload, headers=headers)
    assert resp.status_code == 202
    data = resp.json()
    job_id = data["job_id"]
    analysis_id = data["analysis_id"]
    assert data["status"] == "QUEUED"

    # 2. Poll job status before worker executes -> QUEUED
    poll_resp = await async_client.get(f"/api/v1/analysis/jobs/{analysis_id}", headers=headers)
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["status"] == "QUEUED"
    assert poll_data["attempt_count"] == 0

    # 3. Worker executes the task
    q = get_queue(name=FORENSIC_QUEUE_NAME, connection=fake_sync_redis)
    worker = SimpleWorker([q], connection=fake_sync_redis)
    worker.work(burst=True)

    # 4. Poll again after worker runs -> COMPLETED
    completed_resp = await async_client.get(f"/api/v1/analysis/jobs/{job_id}", headers=headers)
    assert completed_resp.status_code == 200
    completed_data = completed_resp.json()
    assert completed_data["status"] == "COMPLETED"
    assert completed_data["attempt_count"] == 1
    assert completed_data["summary_results"]["test_status"] == "PASSED"
    assert len(completed_data["findings"]) == 1

    # 5. Query analysis history
    history_resp = await async_client.get(
        "/api/v1/analysis/history?status=COMPLETED", headers=headers
    )
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    assert history_data["total"] >= 1
    assert any(item["id"] == analysis_id for item in history_data["items"])


@pytest.mark.asyncio
async def test_idempotency_protection_no_duplicate_jobs(
    test_db_session: AsyncSession,
    fake_sync_redis: Any,
) -> None:
    """Verify that identical idempotency keys prevent duplicate job enqueueing."""
    user, case, evidence = await _create_test_environment(test_db_session)
    service = AnalysisJobService(test_db_session)

    idemp_key = f"IDEMP-{uuid4().hex}"

    # First submission
    job1, created1 = await service.enqueue_analysis(
        evidence_id=evidence.id,
        analysis_type=AnalysisType.TEST_ANALYSIS,
        idempotency_key=idemp_key,
        queue_connection=fake_sync_redis,
    )
    assert created1 is True

    # Second submission with identical idempotency key
    job2, created2 = await service.enqueue_analysis(
        evidence_id=evidence.id,
        analysis_type=AnalysisType.TEST_ANALYSIS,
        idempotency_key=idemp_key,
        queue_connection=fake_sync_redis,
    )
    assert created2 is False
    assert job1.id == job2.id

    # Queue should only contain 1 job
    q = get_queue(name=FORENSIC_QUEUE_NAME, connection=fake_sync_redis)
    assert len(q) == 1


@pytest.mark.asyncio
async def test_finding_deduplication_on_retry(
    test_db_session: AsyncSession,
    fake_sync_redis: Any,
) -> None:
    """Verify findings are cleanly cleared before retrying to prevent finding duplication."""
    user, case, evidence = await _create_test_environment(test_db_session)
    service = AnalysisJobService(test_db_session)

    analysis, _ = await service.enqueue_analysis(
        evidence_id=evidence.id,
        analysis_type=AnalysisType.TEST_ANALYSIS,
        parameters={"simulate_delay": 0},
        queue_connection=fake_sync_redis,
    )

    # Run Attempt 1
    run_analysis_job(str(analysis.id), worker_id="test-worker-1")

    finding_repo = FindingRepository(test_db_session)
    findings_attempt1 = await finding_repo.list_by_analysis(analysis.id)
    assert len(findings_attempt1) == 1

    # Simulate task retry: reset status to QUEUED and re-run Attempt 2
    analysis.status = AnalysisStatus.QUEUED.value
    await test_db_session.commit()

    run_analysis_job(str(analysis.id), worker_id="test-worker-1")

    # Re-query findings: should still have exactly 1 finding, NOT 2!
    findings_attempt2 = await finding_repo.list_by_analysis(analysis.id)
    assert len(findings_attempt2) == 1, "Findings must be deduplicated on task retries!"


@pytest.mark.asyncio
async def test_bounded_retries_and_failure_transition(
    test_db_session: AsyncSession,
    fake_sync_redis: Any,
) -> None:
    """Verify transient failures retry up to max_retries and then transition to FAILED."""
    user, case, evidence = await _create_test_environment(test_db_session)
    service = AnalysisJobService(test_db_session)

    analysis, _ = await service.enqueue_analysis(
        evidence_id=evidence.id,
        analysis_type=AnalysisType.TEST_ANALYSIS,
        parameters={"simulate_failure": "transient"},
        max_retries=2,
        queue_connection=fake_sync_redis,
    )

    # Attempt 1: raises transient exception
    with pytest.raises(RuntimeError, match="Simulated transient failure"):
        run_analysis_job(str(analysis.id))

    await test_db_session.refresh(analysis)
    assert analysis.attempt_count == 1
    assert analysis.error_code == "TRANSIENT_FAILURE"
    assert analysis.status == AnalysisStatus.PROCESSING.value

    # Attempt 2 (exhausts retries): marks FAILED
    with pytest.raises(RuntimeError, match="Exceeded max retries"):
        run_analysis_job(str(analysis.id))

    await test_db_session.refresh(analysis)
    assert analysis.attempt_count == 2
    assert analysis.status == AnalysisStatus.FAILED.value
    assert analysis.error_code == "TRANSIENT_FAILURE_EXHAUSTED"
    assert analysis.completed_at is not None


@pytest.mark.asyncio
async def test_worker_restart_and_crash_recovery(
    test_db_session: AsyncSession,
    fake_sync_redis: Any,
) -> None:
    """Verify interrupted jobs left in PROCESSING by dead workers are restored or failed."""
    user, case, evidence = await _create_test_environment(test_db_session)
    analysis_repo = AnalysisRepository(test_db_session)

    # 1. Create a simulated interrupted job (attempt 1/3, heartbeat 2 hours ago)
    stuck_job = await analysis_repo.create_analysis(
        ForensicAnalysisCreate(
            evidence_id=evidence.id,
            analysis_type=AnalysisType.TEST_ANALYSIS,
            max_retries=3,
        )
    )
    stuck_job.status = AnalysisStatus.PROCESSING.value
    stuck_job.attempt_count = 1
    stuck_job.started_at = datetime.now(UTC) - timedelta(hours=2)
    stuck_job.last_heartbeat_at = datetime.now(UTC) - timedelta(hours=2)
    await test_db_session.commit()

    # 2. Run crash recovery
    service = AnalysisJobService(test_db_session)
    recovered = await service.recover_interrupted_jobs(
        heartbeat_timeout_seconds=60,
        queue_connection=fake_sync_redis,
    )

    assert len(recovered) == 1
    await test_db_session.refresh(stuck_job)
    assert stuck_job.status == AnalysisStatus.QUEUED.value
    assert stuck_job.error_code == "WORKER_CRASHED_RECOVERED"
    assert stuck_job.job_id is not None

    # Re-enqueued job in Redis can now be picked up by the restarted worker!
    q = get_queue(name=FORENSIC_QUEUE_NAME, connection=fake_sync_redis)
    worker = SimpleWorker([q], connection=fake_sync_redis)
    worker.work(burst=True)

    await test_db_session.refresh(stuck_job)
    assert stuck_job.status == AnalysisStatus.COMPLETED.value
    assert stuck_job.summary_results is not None

    # 3. Test exhausted retries crash recovery
    dead_job = await analysis_repo.create_analysis(
        ForensicAnalysisCreate(
            evidence_id=evidence.id,
            analysis_type=AnalysisType.TEST_ANALYSIS,
            max_retries=2,
        )
    )
    dead_job.status = AnalysisStatus.PROCESSING.value
    dead_job.attempt_count = 2  # Already at max retries
    dead_job.started_at = datetime.now(UTC) - timedelta(hours=2)
    dead_job.last_heartbeat_at = datetime.now(UTC) - timedelta(hours=2)
    await test_db_session.commit()

    recovered_dead = await service.recover_interrupted_jobs(
        heartbeat_timeout_seconds=60,
        queue_connection=fake_sync_redis,
    )
    assert len(recovered_dead) == 1
    await test_db_session.refresh(dead_job)
    assert dead_job.status == AnalysisStatus.FAILED.value
    assert dead_job.error_code == "WORKER_CRASHED"
