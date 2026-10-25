"""Case Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.case import CaseStatus


class CaseBase(BaseModel):
    """Base investigation case properties."""

    case_number: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: CaseStatus = CaseStatus.ACTIVE
    lead_investigator_id: UUID | None = None


class CaseCreate(CaseBase):
    """Schema for initializing an investigation case."""

    pass


class CaseUpdate(BaseModel):
    """Schema for updating an existing case."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: CaseStatus | None = None
    lead_investigator_id: UUID | None = None


class CaseRead(CaseBase):
    """Case response schema with metadata timestamps."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
