"""The chunk-log writer the snapshot route tests seed a thread with."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from assistant_core.conversation.event_writer import ChatEventWriter


async def seed_chunks(
    *,
    conversation_id: UUID,
    chunks: list[dict[str, Any]],
) -> None:
    writer = ChatEventWriter(
        conversation_id=conversation_id,
        turn_id=uuid4(),
    )
    for chunk in chunks:
        await writer.write(chunk)
