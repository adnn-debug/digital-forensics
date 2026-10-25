"""
Integration tests for the complete image analysis pipeline.

Verifies:
- End-to-end ingestion and background worker analysis of:
  * Untouched JPEGs
  * Deliberately modified JPEGs
  * Non-JPEG (PNG) formats
- Verification that original file SHA-256 remains 100% intact before and after analysis.
- Separate ELA heatmap artifact generation and storage in vault.
- Database persistence of analysis records, artifacts, and structured findings.
- Content streaming API endpoints for evidence preview and artifact viewing.
"""

from __future__ import annotations

import io
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import pytest
from httpx import AsyncClient
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.db.models.analysis import AnalysisStatus, AnalysisType, ArtifactType
from app.db.models.user import User, UserRole
from app.queue.service import AnalysisJobService
from app.queue.tasks import run_analysis_job
from app.repositories.analysis_repo import AnalysisRepository
from app.repositories.case_repo import CaseRepository
from app.schemas.case import CaseCreate
from app.storage.hasher import MultiHasher
from app.storage.local import LocalFilesystemStorageAdapter


def make_jpeg_bytes(width: int = 240, height: int = 180, quality: int = 95) -> bytes:
    """Generate in-memory valid JPEG bytes."""
    img = Image.new("RGB", (width, height), color=(100, 140, 180))
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 30, 90, 90], fill=(240, 120, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def make_modified_jpeg_bytes(width: int = 240, height: int = 180) -> bytes:
    """Generate in-memory modified JPEG bytes with intentional compression disparity."""
    img = Image.new("RGB", (width, height), color=(90, 90, 90))
    buf1 = io.BytesIO()
    img.save(buf1, format="JPEG", quality=60)
    buf1.seek(0)
    reopened = Image.open(buf1).convert("RGB")

    patch = np.random.randint(0, 255, (40, 40, 3), dtype=np.uint8)
    reopened.paste(Image.fromarray(patch), (120, 30))

    buf2 = io.BytesIO()
    reopened.save(buf2, format="JPEG", quality=95)
    return buf2.getvalue()


def make_png_bytes(width: int = 160, height: int = 120) -> bytes:
    """Generate in-memory valid PNG bytes."""
    img = Image.new("RGBA", (width, height), color=(50, 150, 200, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 20, 80, 80], fill=(255, 255, 0, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
async def examiner_user(test_db_session: AsyncSession) -> User:
    """Create test examiner user."""
    user = User(
        id=uuid4(),
        email=f"examiner_{uuid4().hex[:8]}@forensics.test",
        hashed_password=hash_password("SecureEvidence1234!"),
        full_name="Lead Forensic Examiner",
        role=UserRole.EXAMINER.value,
        is_active=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    return user


class TestImageAnalysisPipeline:
    """Full pipeline verification: Evidence intake -> Worker analysis -> Artifacts & Findings -> API preview."""

    @pytest.mark.asyncio
    async def test_full_image_analysis_workflow(
        self,
        async_client: AsyncClient,
        test_db_session: AsyncSession,
        test_storage_adapter: LocalFilesystemStorageAdapter,
        examiner_user: User,
        fake_sync_redis: Any,
    ) -> None:
        """
        Test untouched JPEG, modified JPEG, and non-JPEG (PNG) through the entire workflow.
        Verify original SHA-256 is unchanged.
        """
        jwt_token = create_access_token(subject=str(examiner_user.id), role=examiner_user.role)
        auth_headers = {"Authorization": f"Bearer {jwt_token}"}

        # 1. Setup Test Case
        case_repo = CaseRepository(test_db_session)
        case = await case_repo.create_case(
            CaseCreate(
                case_number=f"CAS-IMG-{uuid4().hex[:6]}",
                title="Digital Image Analysis Investigation",
                description="Testing JPEG ELA, heatmaps, and format applicability.",
                lead_investigator_id=examiner_user.id,
            )
        )
        await test_db_session.commit()
        case_id = case.id

        # -------------------------------------------------------------------
        # Test Case A: Untouched JPEG Upload & Analysis
        # -------------------------------------------------------------------
        untouched_bytes = make_jpeg_bytes()
        untouched_expected_hash = MultiHasher().hash_bytes(untouched_bytes).sha256

        upload_res = await async_client.post(
            f"/api/v1/cases/{case_id}/evidence/upload",
            files={"file": ("camera_original.jpg", untouched_bytes, "image/jpeg")},
            headers=auth_headers,
        )
        assert upload_res.status_code == 201, upload_res.text
        ev_untouched_data = upload_res.json()
        untouched_ev_id = UUID(ev_untouched_data["id"])
        assert ev_untouched_data["primary_hash_sha256"] == untouched_expected_hash

        # Dispatch JPEG_ELA background task via service
        job_service = AnalysisJobService(test_db_session)
        job_untouched, was_created = await job_service.enqueue_analysis(
            evidence_id=untouched_ev_id,
            analysis_type=AnalysisType.JPEG_ELA,
            parameters={"recompression_quality": 95, "amplification_scale": 15.0},
            initiated_by_id=examiner_user.id,
            queue_connection=fake_sync_redis,
        )
        await test_db_session.commit()
        assert was_created is True

        untouched_job_id = job_untouched.id
        summary_untouched = run_analysis_job(str(untouched_job_id))
        assert summary_untouched["analysis_type"] == AnalysisType.JPEG_ELA.value

        # Refresh session to see updates made by worker
        test_db_session.expire_all()

        # Inspect DB state after execution
        analysis_repo = AnalysisRepository(test_db_session)
        analysis_record = await analysis_repo.get_with_artifacts_and_findings(untouched_job_id)
        assert analysis_record is not None
        assert analysis_record.status == AnalysisStatus.COMPLETED.value
        assert len(analysis_record.artifacts) == 1

        heatmap_artifact = analysis_record.artifacts[0]
        heatmap_artifact_id = heatmap_artifact.id
        assert heatmap_artifact.artifact_type == ArtifactType.ELA_HEATMAP.value
        assert heatmap_artifact.mime_type == "image/png"
        assert test_storage_adapter.exists(heatmap_artifact.storage_path) is True

        # Check physical artifact bytes on disk
        artifact_bytes = test_storage_adapter.read(heatmap_artifact.storage_path)
        assert MultiHasher().hash_bytes(artifact_bytes).sha256 == heatmap_artifact.hash_sha256

        # Check findings and limitations
        assert len(analysis_record.findings) >= 3
        summary = analysis_record.summary_results or {}
        assert "image_properties" in summary
        assert summary["image_properties"]["format"] == "JPEG"
        assert "limitations" in summary

        # INVARIANT: Verify original evidence bitstream is untouched
        current_evidence_bytes = test_storage_adapter.read(ev_untouched_data["storage_path"])
        current_sha256 = MultiHasher().hash_bytes(current_evidence_bytes).sha256
        assert current_sha256 == untouched_expected_hash, "Original JPEG was altered!"

        # -------------------------------------------------------------------
        # Test Case B: Deliberately Modified JPEG Upload & Analysis
        # -------------------------------------------------------------------
        mod_bytes = make_modified_jpeg_bytes()
        mod_expected_hash = MultiHasher().hash_bytes(mod_bytes).sha256

        upload_mod_res = await async_client.post(
            f"/api/v1/cases/{case_id}/evidence/upload",
            files={"file": ("spliced_evidence.jpg", mod_bytes, "image/jpeg")},
            headers=auth_headers,
        )
        assert upload_mod_res.status_code == 201, upload_mod_res.text
        ev_mod_data = upload_mod_res.json()
        mod_ev_id = UUID(ev_mod_data["id"])

        job_modified, _ = await job_service.enqueue_analysis(
            evidence_id=mod_ev_id,
            analysis_type=AnalysisType.JPEG_ELA,
            initiated_by_id=examiner_user.id,
            queue_connection=fake_sync_redis,
        )
        await test_db_session.commit()

        mod_job_id = job_modified.id
        summary_mod = run_analysis_job(str(mod_job_id))
        assert summary_mod["analysis_type"] == AnalysisType.JPEG_ELA.value

        test_db_session.expire_all()
        mod_record = await analysis_repo.get_with_artifacts_and_findings(mod_job_id)
        assert mod_record is not None
        assert mod_record.status == AnalysisStatus.COMPLETED.value
        assert len(mod_record.artifacts) == 1

        # Verify original modified file remains unchanged
        assert (
            MultiHasher().hash_bytes(test_storage_adapter.read(ev_mod_data["storage_path"])).sha256
            == mod_expected_hash
        )

        # -------------------------------------------------------------------
        # Test Case C: Non-JPEG (PNG) Format Upload & Analysis
        # -------------------------------------------------------------------
        png_bytes = make_png_bytes()
        png_expected_hash = MultiHasher().hash_bytes(png_bytes).sha256

        upload_png_res = await async_client.post(
            f"/api/v1/cases/{case_id}/evidence/upload",
            files={"file": ("diagram.png", png_bytes, "image/png")},
            headers=auth_headers,
        )
        assert upload_png_res.status_code == 201, upload_png_res.text
        ev_png_data = upload_png_res.json()
        png_ev_id = UUID(ev_png_data["id"])

        job_png, _ = await job_service.enqueue_analysis(
            evidence_id=png_ev_id,
            analysis_type=AnalysisType.JPEG_ELA,
            initiated_by_id=examiner_user.id,
            queue_connection=fake_sync_redis,
        )
        await test_db_session.commit()

        png_job_id = job_png.id
        summary_png = run_analysis_job(str(png_job_id))
        test_db_session.expire_all()
        png_record = await analysis_repo.get_with_artifacts_and_findings(png_job_id)
        assert png_record is not None
        assert png_record.status == AnalysisStatus.COMPLETED.value

        # For PNG, ELA is marked as not applicable, no heatmap artifact
        assert len(png_record.artifacts) == 0
        assert summary_png["ela"]["is_applicable"] is False
        assert "not applicable" in summary_png["ela"]["inapplicability_reason"].lower()

        # Invariant: original PNG unchanged
        assert (
            MultiHasher().hash_bytes(test_storage_adapter.read(ev_png_data["storage_path"])).sha256
            == png_expected_hash
        )

        # -------------------------------------------------------------------
        # Test Content Streaming API Endpoints
        # -------------------------------------------------------------------
        # 1. Stream original evidence via Bearer token
        res_orig = await async_client.get(
            f"/api/v1/cases/{case_id}/evidence/{untouched_ev_id}/content",
            headers=auth_headers,
        )
        assert res_orig.status_code == 200
        assert res_orig.content == untouched_bytes
        assert "image" in res_orig.headers.get("content-type", "")

        # Also verify stream with ?token= query parameter (for img src)
        res_orig_query = await async_client.get(
            f"/api/v1/cases/{case_id}/evidence/{untouched_ev_id}/content?token={jwt_token}"
        )
        assert res_orig_query.status_code == 200
        assert res_orig_query.content == untouched_bytes

        # 2. Stream artifact heatmap
        res_art = await async_client.get(
            f"/api/v1/analysis/artifacts/{heatmap_artifact_id}/content",
            headers=auth_headers,
        )
        assert res_art.status_code == 200
        assert res_art.content == artifact_bytes
        assert "image/png" in res_art.headers.get("content-type", "")

        # Stream artifact heatmap with ?token= query parameter
        res_art_query = await async_client.get(
            f"/api/v1/analysis/artifacts/{heatmap_artifact_id}/content?token={jwt_token}"
        )
        assert res_art_query.status_code == 200
        assert res_art_query.content == artifact_bytes

        # 3. Fetch Job Status API
        res_job = await async_client.get(
            f"/api/v1/analysis/jobs/{untouched_job_id}",
            headers=auth_headers,
        )
        assert res_job.status_code == 200
        data = res_job.json()
        assert data["status"] == "COMPLETED"
        assert len(data["artifacts"]) == 1
        assert len(data["findings"]) >= 3
        assert data["summary_results"]["image_properties"]["format"] == "JPEG"
