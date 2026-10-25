"""User repository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.repositories.base import BaseRepository
from app.schemas.user import UserCreate


class UserRepository(BaseRepository[User]):
    """Data access repository for User entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        """Find an active user by unique email address."""
        stmt = select(User).where(User.email == email.lower().strip())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(self, payload: UserCreate, hashed_password: str) -> User:
        """Create and persist a new platform user."""
        user = User(
            email=payload.email.lower().strip(),
            hashed_password=hashed_password,
            full_name=payload.full_name,
            role=payload.role.value,
            is_active=payload.is_active,
        )
        return await self.add(user)
