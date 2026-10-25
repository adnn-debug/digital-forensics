"""Forensic Analysis and Artifact Pydantic schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.analysis import AnalysisStatus, AnalysisType, ArtifactType
from app.schemas.finding import FindingRead


# --- Artifact ---
class AnalysisArtifactBase(BaseModel):
    """Base derivative artifact properties."""

    analysis_id: UUID
    artifact_type: ArtifactType
    storage_path: str = Field(min_length=1, max_length=512)
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=128)
    file_size_bytes: int = Field(ge=0)
    hash_sha256: str = Field(min_length=64, max_length=64)
    artifact_metadata: dict[str, Any] | None = None


class AnalysisArtifactCreate(AnalysisArtifactBase):
    """Schema for persisting an analysis artifact."""

    pass


class AnalysisArtifactRead(AnalysisArtifactBase):
    """Analysis artifact response schema."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Forensic Analysis Job ---
class ForensicAnalysisBase(BaseModel):
    """Base analysis job properties."""

    evidence_id: UUID
    analysis_type: AnalysisType
    status: AnalysisStatus = AnalysisStatus.QUEUED
    job_id: str | None = None
    idempotency_key: str | None = None
    attempt_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300
    error_code: str | None = None
    error_message: str | None = None
    parameters: dict[str, Any] | None = None
    summary_results: dict[str, Any] | None = None
    examiner_notes: str | None = None
    worker_id: str | None = None
    initiated_by_id: UUID | None = None


class ForensicAnalysisCreate(BaseModel):
    """Schema for scheduling an analysis job."""

    evidence_id: UUID
    analysis_type: AnalysisType
    parameters: dict[str, Any] | None = None
    examiner_notes: str | None = None
    idempotency_key: str | None = None
    max_retries: int = 3
    timeout_seconds: int = 300
    initiated_by_id: UUID | None = None


class ForensicAnalysisUpdate(BaseModel):
    """Schema for updating job status and results."""

    status: AnalysisStatus | None = None
    job_id: str | None = None
    attempt_count: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    summary_results: dict[str, Any] | None = None
    examiner_notes: str | None = None
    worker_id: str | None = None
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    completed_at: datetime | None = None


class ForensicAnalysisRead(ForensicAnalysisBase):
    """Analysis job response schema."""

    id: UUID
    created_at: datetime
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    artifacts: list[AnalysisArtifactRead] = []
    findings: list[FindingRead] = []

    model_config = ConfigDict(from_attributes=True)


class AnalysisJobCreateResponse(BaseModel):
    """Asynchronous job creation acknowledgement response."""

    job_id: str
    analysis_id: UUID
    evidence_id: UUID
    analysis_type: str
    status: AnalysisStatus
    message: str
    created_at: datetime

