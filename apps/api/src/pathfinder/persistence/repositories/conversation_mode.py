from __future__ import annotations

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.modes import ThreadMode
from pathfinder.persistence.models import ConversationMode


async def read_thread_mode_row(
    session: AsyncSession, *, conversation_id: UUID
) -> ThreadMode | None:
    row = await session.get(ConversationMode, conversation_id, populate_existing=True)
    return None if row is None else row.mode


async def write_thread_mode_row(
    session: AsyncSession, *, conversation_id: UUID, mode: ThreadMode
) -> None:
    await session.execute(
        insert(ConversationMode)
        .values(conversation_id=conversation_id, mode=mode)
        .on_conflict_do_update(
            index_elements=[ConversationMode.conversation_id],
            set_={"mode": mode, "updated_at": func.now()},
        )
    )
