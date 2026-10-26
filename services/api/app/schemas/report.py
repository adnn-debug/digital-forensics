"""Report Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ReportBase(BaseModel):
    """Base examination report properties."""

    case_id: UUID
    report_number: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sha256_hash(self) -> str:
        """Alias for file_hash_sha256 for consistent client-side consumption."""
        return self.file_hash_sha256

    @computed_field  # type: ignore[prop-decorator]
    @property
    def generated_at(self) -> datetime:
        """Alias for created_at representing report generation timestamp."""
        return self.created_at

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_count(self) -> int:
        """Count of exhibits bundled in the report."""
        return len(self.included_evidence_ids or [])


class ReportGenerateRequest(BaseModel):
    """Payload for initiating courtroom report generation."""

    title: str = Field(
        default="Courtroom Evidentiary Examination and Chain of Custody Report",
        max_length=255,
    )
    included_evidence_ids: list[UUID] | None = None
