"""Forensic Finding Pydantic schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.finding import FindingSeverity, FindingType


class FindingBase(BaseModel):
    """Base finding properties."""

    analysis_id: UUID
    evidence_id: UUID
    finding_type: FindingType
    severity: FindingSeverity = FindingSeverity.INFO
    title: str = Field(min_length=1, max_length=255)
    description: str
    confidence_score: float = Field(ge=0.0, le=1.0, default=1.0)
    evidence_offset: str | None = None
    finding_metadata: dict[str, Any] | None = None


class FindingCreate(FindingBase):
    """Schema for recording a forensic finding."""

    pass


class FindingUpdate(BaseModel):
    """Schema for amending a finding or adding examiner notes."""

    severity: FindingSeverity | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_offset: str | None = None
    finding_metadata: dict[str, Any] | None = None


class FindingRead(FindingBase):
    """Finding response schema."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
