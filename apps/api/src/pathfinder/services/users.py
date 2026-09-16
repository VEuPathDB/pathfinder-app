"""User account service - wraps ``UserRepository`` for transport callers."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.user import UserRepository
from pathfinder.platform.config import get_settings


async def get_or_create_user_id(session: AsyncSession, external_id: str) -> UUID:
    """Resolve (or create) the internal user for ``external_id`` and return its id."""
    user = await UserRepository(session).get_or_create_by_external_id(external_id)
    return user.id


async def ensure_user_exists(session: AsyncSession, user_id: UUID) -> None:
    """Persist the authenticated user's row if missing (FK integrity)."""
    await UserRepository(session).get_or_create(user_id)


async def effective_monthly_limit_usd(session: AsyncSession, user_id: UUID) -> Decimal:
    """The budget this user is held to: the account override, else the default."""
    override = await session.scalar(
        select(User.monthly_cost_limit_usd).where(User.id == user_id)
    )
    if override is None:
        return Decimal(str(get_settings().pathfinder_user_monthly_cost_limit_usd))
    return Decimal(str(override))
