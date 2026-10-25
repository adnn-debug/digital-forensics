"""Forensic Case ORM model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.audit import AuditEvent
    from app.db.models.evidence import EvidenceItem
    from app.db.models.report import Report
    from app.db.models.user import User


class CaseStatus(str, enum.Enum):
    """Forensic investigation case lifecycle status."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    CLOSED = "CLOSED"


class Case(Base):
    """Investigation case container for digital evidence."""

    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    case_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=CaseStatus.ACTIVE.value, nullable=False)
    lead_investigator_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    lead_investigator: Mapped["User | None"] = relationship(
        "User",
        back_populates="assigned_cases",
        foreign_keys=[lead_investigator_id],
    )
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        "EvidenceItem",
        back_populates="case",
        cascade="all, delete-orphan",
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="case",
    )
    reports: Mapped[list["Report"]] = relationship(
        "Report",
        back_populates="case",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_cases_status", "status"),
        Index("ix_cases_created_at", "created_at"),
    )
