"""Immutable Chain-of-Custody Audit Event ORM model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.case import Case
    from app.db.models.evidence import EvidenceItem
    from app.db.models.user import User

JSONType = JSON().with_variant(JSONB, "postgresql")


class AuditEventType(str, enum.Enum):
    """Event classifications for chain of custody."""

    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EVIDENCE_INGESTED = "EVIDENCE_INGESTED"
    HASH_VERIFIED = "HASH_VERIFIED"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    METADATA_EXTRACTED = "METADATA_EXTRACTED"
    ANALYSIS_INITIATED = "ANALYSIS_INITIATED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    ARTIFACT_VIEWED = "ARTIFACT_VIEWED"
    REPORT_GENERATED = "REPORT_GENERATED"
    CASE_STATUS_CHANGED = "CASE_STATUS_CHANGED"


class AuditEvent(Base):
    """Append-only, cryptographically chained audit event record."""

    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_description: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    previous_state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_delta: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    case: Mapped["Case | None"] = relationship("Case", back_populates="audit_events")
    evidence: Mapped["EvidenceItem | None"] = relationship(
        "EvidenceItem", back_populates="audit_events"
    )
    user: Mapped["User | None"] = relationship("User", back_populates="audit_events")

    __table_args__ = (
        Index("ix_audit_events_type", "event_type"),
        Index("ix_audit_events_timestamp", "timestamp"),
        Index("ix_audit_events_event_hash", "event_hash"),
    )
