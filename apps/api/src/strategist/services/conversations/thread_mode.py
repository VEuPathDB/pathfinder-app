from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from strategist.domain.modes import ThreadMode
from strategist.persistence.repositories import (
    read_thread_mode_row,
    write_thread_mode_row,
)


async def keep_thread_mode(
    session: AsyncSession, *, conversation_id: UUID, mode: ThreadMode
) -> None:
    await write_thread_mode_row(session, conversation_id=conversation_id, mode=mode)


async def thread_mode_of(session: AsyncSession, conversation_id: UUID) -> ThreadMode:
    kept = await read_thread_mode_row(session, conversation_id=conversation_id)
    return "auto" if kept is None else kept


async def copy_thread_mode(
    session: AsyncSession, *, source_conversation_id: UUID, target_conversation_id: UUID
) -> None:
    kept = await read_thread_mode_row(session, conversation_id=source_conversation_id)
    if kept is not None:
        await write_thread_mode_row(
            session, conversation_id=target_conversation_id, mode=kept
        )
