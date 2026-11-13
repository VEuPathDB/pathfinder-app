"""User repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from strategist.persistence.models import User


class UserRepository:
    """User CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Get user by ID."""
        return await self.session.get(User, user_id)

    async def get_or_create(self, user_id: UUID) -> User:
        """Get existing user or create new one."""
        # Avoid race conditions when multiple concurrent requests attempt to create
        # the same user (e.g. initial page load triggering parallel API calls).
        stmt = (
            pg_insert(User)
            .values(id=user_id)
            .on_conflict_do_nothing(index_elements=[User.id])
        )
        await self.session.execute(stmt)
        user = await self.get_by_id(user_id)
        if user is None:
            # Should be impossible, but keep behavior explicit.
            user = User(id=user_id)
            self.session.add(user)
            await self.session.flush()
        return user

    async def get_or_create_by_external_id(self, external_id: str) -> User:
        """Lookup a user by external identity (e.g. VEuPathDB email).

        Creates a new row if none exists yet, avoiding race conditions with
        ``INSERT ... ON CONFLICT``.
        """
        stmt = (
            pg_insert(User)
            .values(external_id=external_id)
            .on_conflict_do_nothing(index_elements=[User.external_id])
        )
        await self.session.execute(stmt)
        result = await self.session.execute(
            select(User).where(User.external_id == external_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(external_id=external_id)
            self.session.add(user)
            await self.session.flush()
        return user

    async def create(self, external_id: str | None = None) -> User:
        """Create a new user."""
        user = User(external_id=external_id)
        self.session.add(user)
        await self.session.flush()
        return user
