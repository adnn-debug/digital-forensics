"""Report Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportBase(BaseModel):
    """Base examination report properties."""

    case_id: UUID
    report_number: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    examiner_certification: str | None = Field(default=None, max_length=255)
    jurisdiction: str | None = Field(default=None, max_length=255)
    court_name: str | None = Field(default=None, max_length=255)
    docket_number: str | None = Field(default=None, max_length=128)
    classification_marking: str | None = Field(default=None, max_length=128)
    generated_by_id: UUID | None = None
    storage_path: str = Field(min_length=1, max_length=512)
    file_hash_sha256: str = Field(min_length=64, max_length=64)
    file_size_bytes: int = Field(ge=0)
    included_evidence_ids: list[str] | None = None


class ReportCreate(ReportBase):
    """Schema for persisting report metadata."""

    pass


class ReportRead(ReportBase):
    """Report response schema."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportGenerateRequest(BaseModel):
    """Payload for initiating courtroom report generation."""

    title: str = Field(
        default="Courtroom Evidentiary Examination and Chain of Custody Report",
        max_length=255,
    )
    included_evidence_ids: list[UUID] | None = None
    examiner_certification: str | None = Field(default=None, max_length=255)
    jurisdiction: str | None = Field(default=None, max_length=255)
    court_name: str | None = Field(default=None, max_length=255)
    docket_number: str | None = Field(default=None, max_length=128)
    classification_marking: str | None = Field(default=None, max_length=128)
