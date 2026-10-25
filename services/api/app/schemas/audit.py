"""Chain of Custody Audit Event Pydantic schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.audit import AuditEventType


class AuditEventBase(BaseModel):
    """Base audit event properties."""

    case_id: UUID | None = None
    evidence_id: UUID | None = None
    user_id: UUID | None = None
    event_type: AuditEventType
    action_description: str
    ip_address: str | None = None
    user_agent: str | None = None
    previous_state_hash: str | None = Field(default=None, max_length=64)
    event_hash: str = Field(min_length=64, max_length=64)
    payload_delta: dict[str, Any] | None = None


class AuditEventCreate(AuditEventBase):
    """Schema for appending an audit event."""

    pass


class AuditEventRead(AuditEventBase):
    """Audit event response schema."""

    id: UUID
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
