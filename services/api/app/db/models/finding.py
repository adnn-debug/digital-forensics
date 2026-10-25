"""Forensic Finding ORM model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.analysis import ForensicAnalysis
    from app.db.models.evidence import EvidenceItem

JSONType = JSON().with_variant(JSONB, "postgresql")


class FindingSeverity(str, enum.Enum):
    """Severity classification for evidentiary anomalies."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingType(str, enum.Enum):
    """Categorization of forensic detection findings."""

    EXIF_ANOMALY = "EXIF_ANOMALY"
    CONTAINER_MISMATCH = "CONTAINER_MISMATCH"
    ELA_DISPARITY = "ELA_DISPARITY"
    KEYFRAME_INCONSISTENCY = "KEYFRAME_INCONSISTENCY"
    SPECTROGRAM_SPLICE = "SPECTROGRAM_SPLICE"
    HASH_TAMPER = "HASH_TAMPER"
    OTHER = "OTHER"


class Finding(Base):
    """Identified forensic anomaly or evidentiary observation."""

    __tablename__ = "findings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(
        ForeignKey("forensic_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(32),
        default=FindingSeverity.INFO.value,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    evidence_offset: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finding_metadata: Mapped[dict[str, Any] | None] = mapped_column(
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
    analysis: Mapped["ForensicAnalysis"] = relationship("ForensicAnalysis", back_populates="findings")
    evidence: Mapped["EvidenceItem"] = relationship("EvidenceItem", back_populates="findings")

    __table_args__ = (
        Index("ix_findings_severity", "severity"),
        Index("ix_findings_type", "finding_type"),
        Index("ix_findings_created_at", "created_at"),
    )
