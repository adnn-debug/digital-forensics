"""Evidence, Hash Verification, and Metadata Extract ORM models."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.analysis import ForensicAnalysis
    from app.db.models.audit import AuditEvent
    from app.db.models.case import Case
    from app.db.models.finding import Finding
    from app.db.models.user import User

# Cross-database JSON type (JSONB in PostgreSQL, standard JSON in SQLite)
JSONType = JSON().with_variant(JSONB, "postgresql")


class MediaType(str, enum.Enum):
    """Classified media types."""

    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"


class VerificationTrigger(str, enum.Enum):
    """Trigger reasons for evidence re-verification."""

    MANUAL = "MANUAL"
    SCHEDULED_ROUTINE = "SCHEDULED_ROUTINE"
    PRE_ANALYSIS = "PRE_ANALYSIS"
    PRE_REPORT = "PRE_REPORT"


class EvidenceItem(Base):
    """Digital evidence file ingested into a case vault."""

    __tablename__ = "evidence_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_number: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    primary_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hash_md5: Mapped[str] = mapped_column(String(32), nullable=False)
    hash_sha1: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_quarantined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    case: Mapped["Case"] = relationship("Case", back_populates="evidence_items")
    uploaded_by: Mapped["User | None"] = relationship("User", back_populates="uploaded_evidence")
    hash_verifications: Mapped[list["HashVerification"]] = relationship(
        "HashVerification",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )
    metadata_extracts: Mapped[list["MetadataExtract"]] = relationship(
        "MetadataExtract",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )
    forensic_analyses: Mapped[list["ForensicAnalysis"]] = relationship(
        "ForensicAnalysis",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )
    findings: Mapped[list["Finding"]] = relationship(
        "Finding",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="evidence",
    )

    __table_args__ = (
        Index("ix_evidence_items_case_hash", "case_id", "primary_hash_sha256"),
        Index("ix_evidence_items_media_type", "media_type"),
    )


class HashVerification(Base):
    """Cryptographic baseline re-verification audit record."""

    __tablename__ = "hash_verifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    evidence_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculated_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_intact: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verification_trigger: Mapped[str] = mapped_column(
        String(64),
        default=VerificationTrigger.MANUAL.value,
        nullable=False,
    )
    verified_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    evidence: Mapped["EvidenceItem"] = relationship(
        "EvidenceItem", back_populates="hash_verifications"
    )
    verified_by: Mapped["User | None"] = relationship("User", back_populates="hash_verifications")

    __table_args__ = (
        Index("ix_hash_verifications_intact", "is_intact"),
        Index("ix_hash_verifications_verified_at", "verified_at"),
    )


class MetadataExtract(Base):
    """Container and technical metadata extracted via ExifTool or FFprobe."""

    __tablename__ = "metadata_extracts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    evidence_id: Mapped[UUID] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    filtered_forensic_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    evidence: Mapped["EvidenceItem"] = relationship(
        "EvidenceItem", back_populates="metadata_extracts"
    )

    __table_args__ = (Index("ix_metadata_extracts_tool", "tool_name"),)
