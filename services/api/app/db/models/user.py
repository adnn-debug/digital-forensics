"""User and RBAC ORM models."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.audit import AuditEvent
    from app.db.models.case import Case
    from app.db.models.evidence import EvidenceItem, HashVerification
    from app.db.models.report import Report


class UserRole(str, enum.Enum):
    """User authorization roles."""

    ADMIN = "ADMIN"
    EXAMINER = "EXAMINER"
    AUDITOR = "AUDITOR"
    VIEWER = "VIEWER"


class User(Base):
    """Platform user and investigator identity."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.EXAMINER.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    assigned_cases: Mapped[list["Case"]] = relationship(
        "Case",
        back_populates="lead_investigator",
        foreign_keys="Case.lead_investigator_id",
    )
    uploaded_evidence: Mapped[list["EvidenceItem"]] = relationship(
        "EvidenceItem",
        back_populates="uploaded_by",
        foreign_keys="EvidenceItem.uploaded_by_id",
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="user",
        foreign_keys="AuditEvent.user_id",
    )
    hash_verifications: Mapped[list["HashVerification"]] = relationship(
        "HashVerification",
        back_populates="verified_by",
        foreign_keys="HashVerification.verified_by_id",
    )
    generated_reports: Mapped[list["Report"]] = relationship(
        "Report",
        back_populates="generated_by",
        foreign_keys="Report.generated_by_id",
    )
