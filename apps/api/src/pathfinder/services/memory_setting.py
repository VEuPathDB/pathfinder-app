from __future__ import annotations

from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import User
from pathfinder.platform.errors import NotFoundError


class MemorySetting(CamelModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool


async def _load(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError(title="Account not found", detail=str(user_id))
    return user


async def read_memory_setting(session: AsyncSession, user_id: UUID) -> MemorySetting:
    return MemorySetting(enabled=(await _load(session, user_id)).memory_enabled)


async def update_memory_setting(
    session: AsyncSession, user_id: UUID, setting: MemorySetting
) -> MemorySetting:
    user = await _load(session, user_id)
    user.memory_enabled = setting.enabled
    await session.commit()
    return MemorySetting(enabled=user.memory_enabled)


async def the_researchers_store[S](store: S | None, user_id: UUID) -> S | None:
    if store is None:
        return None
    async with async_session_factory() as session:
        enabled = await session.scalar(
            select(User.memory_enabled).where(User.id == user_id)
        )
    return None if enabled is False else store


__all__ = [
    "MemorySetting",
    "read_memory_setting",
    "the_researchers_store",
    "update_memory_setting",
]
