"""Evidence, Verification, and Metadata Extract Pydantic schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.evidence import MediaType, VerificationTrigger


# --- Evidence Item ---
class EvidenceItemBase(BaseModel):
    """Base evidence properties."""

    case_id: UUID
    evidence_number: str = Field(min_length=1, max_length=64)
    original_filename: str = Field(min_length=1, max_length=255)
    stored_filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=128)
    media_type: MediaType
    file_size_bytes: int = Field(ge=0)
    primary_hash_sha256: str = Field(min_length=64, max_length=64)
    hash_md5: str = Field(min_length=32, max_length=32)
    hash_sha1: str = Field(min_length=40, max_length=40)
    storage_path: str = Field(min_length=1, max_length=512)
    is_quarantined: bool = False
    uploaded_by_id: UUID | None = None


class EvidenceItemCreate(EvidenceItemBase):
    """Schema for registering ingested evidence."""

    pass


class EvidenceItemRead(EvidenceItemBase):
    """Evidence item response schema."""

    id: UUID
    ingested_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Hash Verification ---
class HashVerificationBase(BaseModel):
    """Base cryptographic verification properties."""

    evidence_id: UUID
    calculated_sha256: str = Field(min_length=64, max_length=64)
    expected_sha256: str = Field(min_length=64, max_length=64)
    is_intact: bool
    verification_trigger: VerificationTrigger = VerificationTrigger.MANUAL
    verified_by_id: UUID | None = None


class HashVerificationCreate(HashVerificationBase):
    """Schema for recording a verification event."""

    pass


class HashVerificationRead(HashVerificationBase):
    """Hash verification response schema."""

    id: UUID
    verified_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Metadata Extract ---
class MetadataExtractBase(BaseModel):
    """Base technical metadata extraction properties."""

    evidence_id: UUID
    tool_name: str = Field(min_length=1, max_length=64)
    tool_version: str = Field(min_length=1, max_length=32)
    raw_metadata: dict[str, Any]
    filtered_forensic_metadata: dict[str, Any]


class MetadataExtractCreate(MetadataExtractBase):
    """Schema for recording tool extraction results."""

    pass


class MetadataExtractRead(MetadataExtractBase):
    """Metadata extract response schema."""

    id: UUID
    extracted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceDetailRead(EvidenceItemRead):
    """Detailed evidence representation with metadata extracts and hash history."""

    metadata_extracts: list[MetadataExtractRead] = Field(default_factory=list)
    hash_verifications: list[HashVerificationRead] = Field(default_factory=list)


class EvidenceUploadResponse(BaseModel):
    """Secure evidence intake result summary."""

    id: UUID
    case_id: UUID
    evidence_number: str
    original_filename: str
    stored_filename: str
    mime_type: str
    media_type: MediaType
    file_size_bytes: int
    primary_hash_sha256: str
    hash_md5: str
    hash_sha1: str
    storage_path: str
    ingested_at: datetime
    intake_status: str = "INTACT"
    integrity_notice: str = (
        "Cryptographic SHA-256 baseline established at intake. "
        "This hash proves bitstream preservation against the stored vault reference, "
        "but does not guarantee the evidence authenticity or that the file was authentic prior to receipt."
    )

    model_config = ConfigDict(from_attributes=True)


class HashVerificationResult(BaseModel):
    """Cryptographic baseline re-verification result and legal admissibility notice."""

    evidence_id: UUID
    evidence_number: str
    is_intact: bool
    expected_sha256: str
    calculated_sha256: str
    verification_trigger: str
    verified_at: datetime
    integrity_notice: str = (
        "Cryptographic verification confirms that the stored byte stream matches "
        "the reference SHA-256 recorded at the moment of intake (integrity). "
        "It establishes bit-level preservation, but does not prove the authenticity of the evidence "
        "or that the file was authentic and untampered prior to intake."
    )

    model_config = ConfigDict(from_attributes=True)

