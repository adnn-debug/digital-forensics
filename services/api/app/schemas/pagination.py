"""Generic pagination wrapper schemas."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated list response envelope."""

    items: list[T]
    total: int = Field(description="Total number of matching records")
    page: int = Field(description="Current page number (1-based)")
    page_size: int = Field(description="Number of items per page")
    pages: int = Field(description="Total number of pages")
