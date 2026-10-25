"""Background analysis tasks executed by decoupled worker processes."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.db.models.analysis import AnalysisStatus, AnalysisType, ArtifactType
from app.db.models.finding import Finding, FindingSeverity, FindingType
from app.db.session import get_session_maker
from app.forensics.audio_engine import AudioForensicsEngine
from app.forensics.image_engine import ImageForensicsEngine
from app.forensics.metadata_service import MetadataExtractionService
from app.forensics.video_engine import VideoForensicsEngine
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.evidence_repo import EvidenceRepository
from app.repositories.finding_repo import FindingRepository
from app.schemas.analysis import AnalysisArtifactCreate

logger = logging.getLogger("ps05.queue.tasks")


async def _execute_analysis_job_async(
    analysis_id_str: str,
    worker_id: str = "forensic-worker-default",
) -> dict[str, Any]:
    """Asynchronous core execution routine for a forensic analysis task."""
    analysis_id = UUID(analysis_id_str)
    session_factory = get_session_maker()

    async with session_factory() as session:
        analysis_repo = AnalysisRepository(session)
        evidence_repo = EvidenceRepository(session)
        finding_repo = FindingRepository(session)

        analysis = await analysis_repo.get(analysis_id)
        if analysis is None:
            logger.error("Analysis task failed: record %s not found in PostgreSQL", analysis_id)
            return {"status": "ERROR", "error": f"Analysis {analysis_id} not found"}

        # Idempotency protection: do not re-run already finalized tasks
        if analysis.status in (AnalysisStatus.COMPLETED.value, AnalysisStatus.SKIPPED.value):
            logger.info(
                "Task %s is already %s. Skipping duplicate execution.", analysis_id, analysis.status
            )
            return {
                "status": analysis.status,
                "message": "Task already completed",
                "summary": analysis.summary_results,
            }

        # Advance attempt count and transition status to PROCESSING
        current_attempt = (analysis.attempt_count or 0) + 1
        analysis.attempt_count = current_attempt
        analysis.status = AnalysisStatus.PROCESSING.value
        analysis.worker_id = worker_id
        now = datetime.now(UTC)
        if analysis.started_at is None:
            analysis.started_at = now
        analysis.last_heartbeat_at = now
        analysis.error_code = None
        analysis.error_message = None

        await session.commit()
        logger.info(
            "Job %s entered PROCESSING (attempt %d/%d)",
            analysis_id,
            current_attempt,
            analysis.max_retries,
        )

        # Strictly prevent finding duplication on retries: clear any previous findings from failed attempts
        await finding_repo.clear_findings_for_analysis(analysis_id)
        await session.commit()

        # Load evidence item
        evidence = await evidence_repo.get(analysis.evidence_id)
        parameters = analysis.parameters or {}

        try:
            # Handle simulated failures for testing resilience & retry boundaries
            simulate_failure = parameters.get("simulate_failure")
            if simulate_failure == "transient":
                if current_attempt < analysis.max_retries:
                    analysis.error_code = "TRANSIENT_FAILURE"
                    analysis.error_message = f"Simulated transient error on attempt {current_attempt}/{analysis.max_retries}"
                    analysis.last_heartbeat_at = datetime.now(UTC)
                    await session.commit()
                    logger.warning(
                        "Simulated transient error on job %s attempt %d. Triggering RQ retry.",
                        analysis_id,
                        current_attempt,
                    )
                    raise RuntimeError(f"Simulated transient failure on attempt {current_attempt}")
                else:
                    # Final attempt reached
                    analysis.status = AnalysisStatus.FAILED.value
                    analysis.error_code = "TRANSIENT_FAILURE_EXHAUSTED"
                    analysis.error_message = (
                        f"Transient error exceeded maximum attempts ({analysis.max_retries})"
                    )
                    analysis.completed_at = datetime.now(UTC)
                    await session.commit()
                    logger.error(
                        "Job %s exhausted all %d retries.", analysis_id, analysis.max_retries
                    )
                    raise RuntimeError(
                        f"Exceeded max retries ({analysis.max_retries}) for transient error"
                    )

            elif simulate_failure == "permanent":
                analysis.status = AnalysisStatus.FAILED.value
                analysis.error_code = "PERMANENT_ERROR"
                analysis.error_message = "Simulated fatal error: file corrupt or invalid parameters"
                analysis.completed_at = datetime.now(UTC)
                await session.commit()
                return {"status": "FAILED", "error_code": "PERMANENT_ERROR"}

            # Simulated processing duration
            simulate_delay = parameters.get("simulate_delay")
            if simulate_delay and float(simulate_delay) > 0:
                delay = min(float(simulate_delay), 30.0)
                logger.info("Simulating forensic processing delay: %.2fs", delay)
                await asyncio.sleep(delay)

            findings_to_create = []

            # -------------------------------------------------------------
            # Branch 1: JPEG Error Level Analysis (ELA) & Image Forensics
            # -------------------------------------------------------------
            if analysis.analysis_type in (AnalysisType.JPEG_ELA.value, "JPEG_ELA", "IMAGE_ANALYSIS"):
                if evidence is None:
                    raise ValueError(f"Evidence item {analysis.evidence_id} not found in database.")

                from app.api.deps import get_storage_adapter

                adapter = get_storage_adapter()
                physical_path = adapter.get_local_path_readonly(evidence.storage_path)

                quality_param = parameters.get("recompression_quality") or parameters.get("quality")
                quality = int(quality_param) if quality_param is not None else 95
                scale_param = parameters.get("amplification_scale") or parameters.get("scale")
                scale = float(scale_param) if scale_param is not None else 15.0

                engine = ImageForensicsEngine(default_quality=quality, default_scale=scale)
                result = engine.analyze_file(
                    file_path=physical_path,
                    expected_sha256=evidence.primary_hash_sha256,
                    quality=quality,
                    scale=scale,
                    evidence_number=evidence.evidence_number,
                )

                # Persist ELA Heatmap Artifact if generated
                if result.ela.heatmap_bytes and result.ela.heatmap_filename:
                    artifact_key = adapter.generate_key(
                        category="artifacts",
                        case_id=evidence.case_id,
                        filename=result.ela.heatmap_filename,
                    )
                    adapter.write(artifact_key, result.ela.heatmap_bytes)

                    artifact_payload = AnalysisArtifactCreate(
                        analysis_id=analysis_id,
                        artifact_type=ArtifactType.ELA_HEATMAP,
                        storage_path=artifact_key,
                        file_name=result.ela.heatmap_filename,
                        mime_type=result.ela.heatmap_mime_type or "image/png",
                        file_size_bytes=result.ela.heatmap_size_bytes or len(result.ela.heatmap_bytes),
                        hash_sha256=result.ela.heatmap_sha256 or "",
                        artifact_metadata=result.ela.provenance,
                    )
                    await analysis_repo.create_artifact(artifact_payload)

                # Persist Structured Findings
                for f_dto in result.findings:
                    finding = Finding(
                        analysis_id=analysis_id,
                        evidence_id=evidence.id,
                        finding_type=f_dto.finding_type,
                        severity=f_dto.severity,
                        title=f_dto.title,
                        description=f_dto.description,
                        confidence_score=f_dto.confidence_score,
                        evidence_offset=f_dto.evidence_offset,
                        finding_metadata=f_dto.finding_metadata,
                    )
                    session.add(finding)
                    findings_to_create.append(finding)

                summary = result.to_summary_dict()
                summary["analysis_type"] = analysis.analysis_type
                summary["evidence_id"] = str(analysis.evidence_id)
                summary["evidence_number"] = evidence.evidence_number
                summary["sha256"] = evidence.primary_hash_sha256
                summary["attempt_count"] = current_attempt

            # -------------------------------------------------------------
            # Branch 2: Forensic Technical Metadata Extraction (ExifTool / FFprobe)
            # -------------------------------------------------------------
            elif analysis.analysis_type in (
                AnalysisType.METADATA_EXTRACTION.value,
                "METADATA_EXTRACTION",
            ):
                if evidence is None:
                    raise ValueError(f"Evidence item {analysis.evidence_id} not found in database.")

                from app.api.deps import get_storage_adapter

                adapter = get_storage_adapter()
                meta_service = MetadataExtractionService(session, adapter)
                extracts = await meta_service.extract_and_persist(
                    evidence, current_user_id=analysis.initiated_by_id
                )

                finding = Finding(
                    analysis_id=analysis_id,
                    evidence_id=evidence.id,
                    finding_type=FindingType.EXIF_ANOMALY.value,
                    severity=FindingSeverity.INFO.value,
                    title="Container & Stream Metadata Extracted",
                    description=(
                        f"Technical metadata successfully extracted via {len(extracts)} forensic tool suite(s). "
                        f"Tools: {', '.join(e.tool_name for e in extracts)}."
                    ),
                    confidence_score=1.0,
                    evidence_offset="0x00000000",
                    finding_metadata={"tools_executed": [e.tool_name for e in extracts]},
                )
                session.add(finding)
                findings_to_create.append(finding)

                summary = {
                    "analysis_type": analysis.analysis_type,
                    "evidence_id": str(analysis.evidence_id),
                    "evidence_number": evidence.evidence_number,
                    "sha256": evidence.primary_hash_sha256,
                    "attempt_count": current_attempt,
                    "extracts_count": len(extracts),
                    "tools": [e.tool_name for e in extracts],
                    "completed_at": datetime.now(UTC).isoformat(),
                }

            # -------------------------------------------------------------
            # Branch 3: Video Keyframes & Temporal Slicing Analysis
            # -------------------------------------------------------------
            elif analysis.analysis_type in (
                AnalysisType.VIDEO_FRAMES.value,
                "VIDEO_FRAMES",
                "VIDEO_ANALYSIS",
            ):
                if evidence is None:
                    raise ValueError(f"Evidence item {analysis.evidence_id} not found in database.")

                from app.api.deps import get_storage_adapter

                adapter = get_storage_adapter()
                physical_path = adapter.get_local_path_readonly(evidence.storage_path)

                max_kf = int(parameters.get("max_keyframes", 10))
                raw_ts = parameters.get("timestamps")
                timestamps_param: list[float] | None = None
                if isinstance(raw_ts, list):
                    try:
                        timestamps_param = [float(t) for t in raw_ts]
                    except (ValueError, TypeError):
                        timestamps_param = None

                video_engine = VideoForensicsEngine(max_keyframes=max_kf)
                vid_result = video_engine.analyze_file(
                    file_path=physical_path,
                    expected_sha256=evidence.primary_hash_sha256,
                    evidence_number=evidence.evidence_number,
                    timestamps=timestamps_param,
                )

                # Persist extracted keyframe artifacts
                for kf in vid_result.keyframes:
                    artifact_key = adapter.generate_key(
                        category="artifacts",
                        case_id=evidence.case_id,
                        filename=kf.filename,
                    )
                    adapter.write(artifact_key, kf.image_bytes)

                    artifact_payload = AnalysisArtifactCreate(
                        analysis_id=analysis_id,
                        artifact_type=ArtifactType.KEYFRAME_IMAGE,
                        storage_path=artifact_key,
                        file_name=kf.filename,
                        mime_type=kf.mime_type,
                        file_size_bytes=len(kf.image_bytes),
                        hash_sha256=kf.sha256,
                        artifact_metadata={
                            "frame_index": kf.frame_index,
                            "timestamp_seconds": kf.timestamp_seconds,
                            "dhash": kf.dhash,
                            "is_scene_change": kf.is_scene_change,
                        },
                    )
                    await analysis_repo.create_artifact(artifact_payload)

                # Persist structured findings
                for f_dto in vid_result.findings:
                    finding = Finding(
                        analysis_id=analysis_id,
                        evidence_id=evidence.id,
                        finding_type=f_dto.finding_type,
                        severity=f_dto.severity,
                        title=f_dto.title,
                        description=f_dto.description,
                        confidence_score=f_dto.confidence_score,
                        evidence_offset=f_dto.evidence_offset,
                        finding_metadata=f_dto.finding_metadata,
                    )
                    session.add(finding)
                    findings_to_create.append(finding)

                summary = vid_result.to_summary_dict()
                summary["analysis_type"] = analysis.analysis_type
                summary["evidence_id"] = str(analysis.evidence_id)
                summary["evidence_number"] = evidence.evidence_number
                summary["sha256"] = evidence.primary_hash_sha256
                summary["attempt_count"] = current_attempt

            # -------------------------------------------------------------
            # Branch 4: Audio STFT Spectrogram & Waveform Analysis
            # -------------------------------------------------------------
            elif analysis.analysis_type in (
                AnalysisType.AUDIO_SPECTROGRAM.value,
                "AUDIO_SPECTROGRAM",
                "AUDIO_ANALYSIS",
            ):
                if evidence is None:
                    raise ValueError(f"Evidence item {analysis.evidence_id} not found in database.")

                from app.api.deps import get_storage_adapter

                adapter = get_storage_adapter()
                physical_path = adapter.get_local_path_readonly(evidence.storage_path)

                audio_engine = AudioForensicsEngine()
                aud_result = audio_engine.analyze_file(
                    file_path=physical_path,
                    expected_sha256=evidence.primary_hash_sha256,
                    evidence_number=evidence.evidence_number,
                    parameters=parameters,
                )

                # Persist Spectrogram Artifact
                if aud_result.spectrogram_artifact:
                    spec = aud_result.spectrogram_artifact
                    artifact_key = adapter.generate_key(
                        category="artifacts",
                        case_id=evidence.case_id,
                        filename=spec.filename,
                    )
                    adapter.write(artifact_key, spec.image_bytes)

                    artifact_payload = AnalysisArtifactCreate(
                        analysis_id=analysis_id,
                        artifact_type=ArtifactType.SPECTROGRAM_PNG,
                        storage_path=artifact_key,
                        file_name=spec.filename,
                        mime_type=spec.mime_type,
                        file_size_bytes=len(spec.image_bytes),
                        hash_sha256=spec.sha256,
                        artifact_metadata={
                            "nyquist_hz": aud_result.spectral_metrics.nyquist_frequency_hz,
                            "cutoff_hz": aud_result.spectral_metrics.detected_cutoff_frequency_hz,
                            "width": spec.width,
                            "height": spec.height,
                        },
                    )
                    await analysis_repo.create_artifact(artifact_payload)

                # Persist Waveform Artifact
                if aud_result.waveform_artifact:
                    wave_art = aud_result.waveform_artifact
                    artifact_key = adapter.generate_key(
                        category="artifacts",
                        case_id=evidence.case_id,
                        filename=wave_art.filename,
                    )
                    adapter.write(artifact_key, wave_art.image_bytes)

                    artifact_payload = AnalysisArtifactCreate(
                        analysis_id=analysis_id,
                        artifact_type=ArtifactType.WAVEFORM_PNG,
                        storage_path=artifact_key,
                        file_name=wave_art.filename,
                        mime_type=wave_art.mime_type,
                        file_size_bytes=len(wave_art.image_bytes),
                        hash_sha256=wave_art.sha256,
                        artifact_metadata={
                            "duration_seconds": aud_result.properties.duration_seconds,
                            "rms_amplitude": aud_result.properties.rms_amplitude,
                            "width": wave_art.width,
                            "height": wave_art.height,
                        },
                    )
                    await analysis_repo.create_artifact(artifact_payload)

                # Persist findings
                for f_dto in aud_result.findings:
                    finding = Finding(
                        analysis_id=analysis_id,
                        evidence_id=evidence.id,
                        finding_type=f_dto.finding_type,
                        severity=f_dto.severity,
                        title=f_dto.title,
                        description=f_dto.description,
                        confidence_score=f_dto.confidence_score,
                        evidence_offset=f_dto.evidence_offset,
                        finding_metadata=f_dto.finding_metadata,
                    )
                    session.add(finding)
                    findings_to_create.append(finding)

                summary = aud_result.to_summary_dict()
                summary["analysis_type"] = analysis.analysis_type
                summary["evidence_id"] = str(analysis.evidence_id)
                summary["evidence_number"] = evidence.evidence_number
                summary["sha256"] = evidence.primary_hash_sha256
                summary["attempt_count"] = current_attempt

            # -------------------------------------------------------------
            # Branch 5: Standard Test Analysis Job
            # -------------------------------------------------------------
            else:
                if evidence is not None:
                    finding = Finding(
                        analysis_id=analysis_id,
                        evidence_id=evidence.id,
                        finding_type=FindingType.OTHER.value,
                        severity=FindingSeverity.INFO.value,
                        title="Evidentiary Baseline Validated",
                        description=(
                            f"Automated forensic verification succeeded on attempt {current_attempt}. "
                            f"Original filename: '{evidence.original_filename}', SHA-256: {evidence.primary_hash_sha256}"
                        ),
                        confidence_score=1.0,
                        evidence_offset="0x00000000",
                        finding_metadata={
                            "attempt": current_attempt,
                            "primary_hash": evidence.primary_hash_sha256,
                            "media_type": evidence.media_type,
                        },
                    )
                    session.add(finding)
                    findings_to_create.append(finding)

                summary = {
                    "test_status": "PASSED",
                    "analysis_type": analysis.analysis_type,
                    "evidence_id": str(analysis.evidence_id),
                    "evidence_number": evidence.evidence_number if evidence else "UNKNOWN",
                    "sha256": evidence.primary_hash_sha256 if evidence else None,
                    "attempt_count": current_attempt,
                    "findings_count": len(findings_to_create),
                    "completed_at": datetime.now(UTC).isoformat(),
                }

            analysis.status = AnalysisStatus.COMPLETED.value
            analysis.summary_results = summary
            analysis.completed_at = datetime.now(UTC)
            analysis.error_code = None
            analysis.error_message = None

            await session.commit()
            logger.info("Job %s completed successfully in PostgreSQL.", analysis_id)
            return summary

        except Exception as exc:
            # If not already marked failed and within retries, re-raise for RQ retry
            if analysis.status != AnalysisStatus.FAILED.value:
                if current_attempt < analysis.max_retries:
                    analysis.error_code = "TRANSIENT_FAILURE"
                    analysis.error_message = str(exc)
                    analysis.last_heartbeat_at = datetime.now(UTC)
                    await session.commit()
                else:
                    analysis.status = AnalysisStatus.FAILED.value
                    analysis.error_code = "MAX_RETRIES_EXCEEDED"
                    analysis.error_message = f"Failed after {current_attempt} attempts: {exc}"
                    analysis.completed_at = datetime.now(UTC)
                    await session.commit()
            raise


def run_analysis_job(
    analysis_id_str: str,
    worker_id: str = "forensic-worker-default",
) -> dict[str, Any]:
    """
    Synchronous entrypoint called by RQ Worker child processes.
    Bridges execution into the async SQLAlchemy engine.
    Safely handles both dedicated worker processes and in-thread test runners.
    """
    logger.info("Worker process dispatched job for analysis: %s", analysis_id_str)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda: asyncio.run(
                    _execute_analysis_job_async(analysis_id_str, worker_id=worker_id)
                )
            )
            return future.result()

    return asyncio.run(_execute_analysis_job_async(analysis_id_str, worker_id=worker_id))
