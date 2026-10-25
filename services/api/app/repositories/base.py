"""Generic asynchronous SQLAlchemy repository base."""

from collections.abc import Sequence
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async repository providing standard entity persistence operations."""

    def __init__(self, session: AsyncSession, model_cls: type[ModelT]) -> None:
        self.session = session
        self.model_cls = model_cls

    async def get_by_id(self, entity_id: UUID) -> ModelT | None:
        """Fetch a single entity by primary key UUID."""
        stmt = select(self.model_cls).where(self.model_cls.id == entity_id)  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    get = get_by_id

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        """Fetch a paginated sequence of entities."""
        stmt = select(self.model_cls).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Return total row count for the entity table."""
        stmt = select(func.count()).select_from(self.model_cls)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    async def add(self, entity: ModelT) -> ModelT:
        """Stage an entity in the current session."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        """Mark an entity for deletion."""
        await self.session.delete(entity)
        await self.session.flush()
