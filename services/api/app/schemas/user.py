"""User Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.user import UserRole


class UserBase(BaseModel):
    """Base user properties."""

    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.EXAMINER
    is_active: bool = True


class UserCreate(UserBase):
    """Schema for registering a new user."""

    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    """Schema for updating an existing user."""

    email: str | None = Field(default=None, min_length=3, max_length=255)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserRead(UserBase):
    """User response schema without password hash."""

    id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
