"""Forensic Analysis and Derivative Artifact ORM models."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.evidence import EvidenceItem
    from app.db.models.finding import Finding
    from app.db.models.user import User

JSONType = JSON().with_variant(JSONB, "postgresql")


class AnalysisType(str, enum.Enum):
    """Supported forensic analysis heuristics."""

    TEST_ANALYSIS = "TEST_ANALYSIS"
    JPEG_ELA = "JPEG_ELA"
    VIDEO_FRAMES = "VIDEO_FRAMES"
    AUDIO_SPECTROGRAM = "AUDIO_SPECTROGRAM"
    METADATA_EXTRACTION = "METADATA_EXTRACTION"


class AnalysisStatus(str, enum.Enum):
    """Lifecycle status of a background forensic analysis."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

    # Backward compatibility aliases
    PENDING = "QUEUED"
    IN_PROGRESS = "PROCESSING"


class ArtifactType(str, enum.Enum):
    """Classification of forensic derivative artifacts."""

    ELA_HEATMAP = "ELA_HEATMAP"
    KEYFRAME_IMAGE = "KEYFRAME_IMAGE"
    SPECTROGRAM_PNG = "SPECTROGRAM_PNG"
    WAVEFORM_PNG = "WAVEFORM_PNG"
    TEST_OUTPUT = "TEST_OUTPUT"


class ForensicAnalysis(Base):
    """Execution record of a deep forensic heuristic task."""

    __tablename__ = "forensic_analyses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    evidence_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=AnalysisStatus.QUEUED.value,
        nullable=False,
    )
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    summary_results: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    examiner_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    initiated_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    evidence: Mapped["EvidenceItem"] = relationship(
        "EvidenceItem", back_populates="forensic_analyses"
    )
    initiated_by: Mapped["User | None"] = relationship("User")
    artifacts: Mapped[list["AnalysisArtifact"]] = relationship(
        "AnalysisArtifact",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    findings: Mapped[list["Finding"]] = relationship(
        "Finding",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_forensic_analyses_status", "status"),
        Index("ix_forensic_analyses_type", "analysis_type"),
        Index("ix_forensic_analyses_job_id", "job_id"),
        Index("ix_forensic_analyses_idempotency", "idempotency_key"),
    )


class AnalysisArtifact(Base):
    """Derivative forensic visualization or output file (e.g. ELA map, spectrogram)."""

    __tablename__ = "analysis_artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("forensic_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONType,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    analysis: Mapped["ForensicAnalysis"] = relationship(
        "ForensicAnalysis", back_populates="artifacts"
    )

    __table_args__ = (
        Index("ix_analysis_artifacts_type", "artifact_type"),
        Index("ix_analysis_artifacts_hash", "hash_sha256"),
    )
